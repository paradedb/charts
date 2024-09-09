# CNPGInstanceMetricsFailing

## Description

The `CNPGInstanceMetricsFailing` alert is triggered when a CloudNativePG instance's metrics collector reports that its most recent collection ended in an error for 15 minutes. The delay is long enough to ride out a single failed collection cycle, a restart or a failover, so when the alert fires the failure is persistent rather than transient.

This is the counterpart to `CNPGInstanceMetricsAbsent`. That alert covers an exporter that has stopped responding, which is visible from outside. This one covers an exporter that responds normally while the queries behind individual metrics fail, which is not.

## Impact

The instance keeps serving queries. The risk is in the series that stop being published, because the alerts that read them are all `expr > threshold` rules: with no samples to evaluate they produce nothing rather than firing. They fail open, silently.

Which alerts go blind depends on which queries are failing. If the collector cannot reach the application database, every default per-database query fails at once and that includes:

- `CNPGClusterPhysicalReplicationLag*`, which reads `cnpg_pg_replication_lag`
- `CNPGClusterHA*`, which reads `cnpg_pg_replication_streaming_replicas` and `cnpg_pg_replication_is_wal_receiver_up`
- The logical replication alerts, which read `cnpg_pg_stat_subscription_*`

A standby in this state has previously replayed nothing for two months without alerting, because the one rule aimed squarely at that condition had no series to evaluate.

## Diagnosis

The alert labels carry the `namespace`, `cluster` and `pod`.

- Confirm the collector is up but erroring. `cnpg_collector_up` reads 1 and `cnpg_collector_last_collection_error` reads 1 at the same time, which is the whole signature:

```bash
kubectl exec -n <namespace> -it pod/<instance-pod-name> -- curl -sS --max-time 5 http://localhost:9187/metrics | grep -E "cnpg_collector_up|cnpg_collector_last_collection_error"
```

- Find which query is failing. The instance logs name both the query and the database it could not reach:

```bash
kubectl logs -n <namespace> pod/<instance-pod-name> --tail=200 | grep -i "error collecting"
```

A line naming a `targetDatabase` the cluster does not have is the common case:

```
"Error collecting user query","query":"pg_settings","targetDatabase":"app"
```

- Check what the application database is actually called. The collector queries the name in `.spec.bootstrap.initdb.database`, and a cluster bootstrapped without one gets `app` by default:

```bash
kubectl get -n <namespace> cluster/paradedb -o jsonpath='{.spec.bootstrap.initdb.database}'
kubectl exec -n <namespace> -it pod/<instance-pod-name> -- psql -lqt | cut -d '|' -f 1
```

If the two disagree, that is the fault. A dedicated replica declared as its own cluster is the easiest place to get this wrong, because the database name has to be repeated there and is easy to leave out.

- Confirm which series are actually missing, so you know what was unmonitored:

```bash
kubectl exec -n <namespace> -it pod/<instance-pod-name> -- curl -sS --max-time 5 http://localhost:9187/metrics | grep -cE "cnpg_pg_replication_lag|cnpg_pg_replication_streaming_replicas"
```

- On a standby, check from the primary whether replication is healthy, since the lag alerts could not have told you:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
SELECT application_name, state, replay_lsn, replay_lag FROM pg_stat_replication;
"
```

## Mitigation

- If the application database name is wrong, correct it on the cluster and let the operator roll the change out. On a dedicated replica, set it to the same name the source cluster uses.

- If the failure is a custom monitoring query rather than a default one, disable that instrumentation under `.spec.monitoring` until a fixed version is rolled out. The default collectors keep working, so the alerts above stay live.

- If a collector query is blocked rather than erroring outright, terminate the backend holding it up:

```bash
kubectl exec -n <namespace> -it pod/<instance-pod-name> -- psql -c "
SELECT pid, state, wait_event_type, wait_event,
       now() - query_start AS duration, left(query, 120) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY duration DESC NULLS LAST;
"
kubectl exec -n <namespace> -it pod/<instance-pod-name> -- psql -c "SELECT pg_terminate_backend(<pid>);"
```

The alert resolves once a collection completes without error. Confirm the missing series are back:

```bash
kubectl exec -n <namespace> -it pod/<instance-pod-name> -- curl -sS --max-time 5 http://localhost:9187/metrics | grep -E "cnpg_collector_last_collection_error|cnpg_pg_replication_lag"
```

Afterwards, audit whether any replication or HA alert should have fired while the series were missing, and for how long they had been missing before this alert existed. Escalate if the collection error persists after the database name is correct, if it appears across several instances at once, which suggests a bad instrumentation rollout rather than one misconfigured cluster, or if `pg_stat_replication` on the primary shows a standby that has not been replaying.
