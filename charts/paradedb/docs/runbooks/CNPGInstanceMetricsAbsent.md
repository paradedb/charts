# CNPGInstanceMetricsAbsent

## Description

The `CNPGInstanceMetricsAbsent` alert is triggered when a CloudNativePG instance's metrics endpoint has been unreachable for 10 minutes while the pod itself is still running. The delay is long enough to ride out routine restarts, upgrades, drains and scale-downs, so when the alert fires the instance is up but its exporter is hung.

## Impact

The instance keeps serving queries, so the risk is in what the missing metrics hide. The lag, HA and replication alerts all read from this exporter:

- `CNPGClusterPhysicalReplicationLag*` reads `cnpg_pg_replication_lag`
- `CNPGClusterHA*` reads `cnpg_pg_replication_streaming_replicas` and `cnpg_pg_replication_is_wal_receiver_up`
- The logical replication alerts read `cnpg_pg_stat_subscription_*`

These are all `expr > threshold` rules, so once the exporter goes silent there are no samples to evaluate and they cannot fire. While this alert is active, their silence means nothing for this instance. A hung exporter has previously coincided with a frozen standby, where replication was stuck and nothing alerted on it.

## Diagnosis

The alert labels carry the `namespace`, `cluster` and `pod`.

- Confirm the pod is up. `Running` and `Ready` means the instance itself is healthy and only its exporter has failed:

```bash
kubectl get -n <namespace> pods -l "cnpg.io/podRole=instance" -o wide
kubectl describe -n <namespace> pod/<instance-pod-name>
```

- Check the metrics endpoint. The collector serves `/metrics` on port `9187`, and a hung exporter times out here while the pod stays Ready:

```bash
kubectl exec -n <namespace> -it pod/<instance-pod-name> -- curl -sS --max-time 5 http://localhost:9187/metrics | grep cnpg_collector_up
```

A timeout or empty response confirms the collector is stuck.

- Look for a blocked backend. The exporter runs SQL on the local instance, so a stuck collector query shows up in `pg_stat_activity`:

```bash
kubectl exec -n <namespace> -it pod/<instance-pod-name> -- psql -c "
SELECT pid, state, wait_event_type, wait_event,
       now() - query_start AS duration, left(query, 120) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY duration DESC NULLS LAST;
"
```

- On a standby, check from the primary whether replay is actually frozen:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
SELECT application_name, state, replay_lsn, replay_lag FROM pg_stat_replication;
"
```

- Inspect the instance and operator logs for collector errors, statement timeouts, or recovery conflict and deadlock messages:

```bash
kubectl logs -n <namespace> pod/<instance-pod-name> --tail=200
kubectl logs -n cnpg-system -l "app.kubernetes.io/name=cloudnative-pg" --tail=200
```

## Mitigation

- Terminate the stuck backend, if the diagnosis found one:

```bash
kubectl exec -n <namespace> -it pod/<instance-pod-name> -- psql -c "SELECT pg_terminate_backend(<pid>);"
```

- If the hang comes from a custom monitoring query, disable that instrumentation in the cluster's `.spec.monitoring` configuration until a fixed version is rolled out.

- As a last resort, recycle the pod. Start with a standby, never the primary, to avoid an unnecessary failover:

```bash
kubectl delete -n <namespace> pod/<replica-pod-name>
```

The alert resolves once the endpoint responds again. Confirm metrics are flowing:

```bash
kubectl exec -n <namespace> -it pod/<instance-pod-name> -- curl -sS --max-time 5 http://localhost:9187/metrics | grep -E "cnpg_collector_up|cnpg_pg_replication_lag"
```

Afterwards, audit whether any replication or HA alert should have fired while the exporter was down. Escalate if the endpoint stays unresponsive after terminating stuck backends, if `pg_stat_replication` on the primary shows replay frozen for the affected standby, or if the collector hangs repeatedly or across several instances, which suggests a systemic instrumentation or engine bug.
