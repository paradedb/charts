# CNPGInstanceMetricsAbsent

## Description

The `CNPGInstanceMetricsAbsent` alert fires when a CloudNativePG instance is **Ready** according to Kubernetes but has **stopped exporting CloudNativePG collector metrics** (`cnpg_collector_up` and every other `cnpg_*` series produced by that pod), after having reported them within the previous hour.

The alert deliberately gates on pod readiness so it does *not* fire for routine churn:

- A restarting, upgrading, draining, or scaling-down instance is either absent or `NotReady`, so it is excluded.
- A pod that is `Ready` but silent is a running database instance whose **metrics exporter has gone dark** — a monitoring blind spot, not a maintenance event.

Readiness is read from `kube-state-metrics` (`kube_pod_status_ready`), which is a *separate* exporter from the in-pod CNPG collector. That independence is the whole point: it stays healthy and keeps reporting even when the instance's own collector is wedged.

## Impact

This alert is **critical because of what it hides, not what it directly breaks**.

Most replication and health alerts evaluate metrics emitted by this exact exporter:

- `PhysicalReplicationLagHigh` / `PhysicalReplicationLagCritical` → `cnpg_pg_replication_lag`
- `CNPGClusterHAWarning` / `CNPGClusterHACritical` → `cnpg_pg_replication_streaming_replicas`, `cnpg_pg_replication_is_wal_receiver_up`
- Logical replication alerts → `cnpg_pg_stat_subscription_*`

These are all `expr > threshold` rules. When the exporter goes silent there are **no samples to evaluate**, so the expression returns an empty result and the alert **never enters pending or firing** — no-data is silence, not a page. In other words, while this alert is firing you should assume the other replication/HA alerts for this instance are **blind and cannot be trusted**.

A known real-world trigger: an instrumentation query (`paradedb.index_info`) deadlocked when run on a standby, which simultaneously **froze WAL replay on that standby** *and* **wedged the standby's metrics collector**. Replication was stuck for an extended period with no notification, precisely because the thing that measures replication lag had stopped reporting it.

## Diagnosis

### Step 1: Identify the affected instance

The alert labels carry `customer`, `namespace`, `cluster`, and `pod`. Confirm the pod is genuinely up:

```bash
kubectl get pods --namespace <namespace> -l "cnpg.io/podRole=instance" -o wide
kubectl describe pod --namespace <namespace> <pod-name>
```

If the pod is `Running` and `Ready`, this is a true positive: the instance is alive but blind.

### Step 2: Check whether the metrics endpoint is responding

The collector serves metrics on port `9187` at `/metrics`. A hung exporter will hang or time out here while the pod stays Ready:

```bash
# From inside the pod (curl may not be present; wget/psql checks below also work)
kubectl exec --namespace <namespace> <pod-name> -- \
  curl -sS --max-time 5 http://localhost:9187/metrics | head

# Or port-forward and scrape from your workstation
kubectl port-forward --namespace <namespace> pod/<pod-name> 9187:9187
curl -sS --max-time 5 http://localhost:9187/metrics | grep cnpg_collector_up
```

A timeout / empty response confirms the collector is wedged.

### Step 3: Look for a blocked or deadlocked backend

The exporter runs SQL against the local instance. If a collector query is stuck (often on a standby, against recovery conflict or an instrumentation function), it shows up in `pg_stat_activity`:

```bash
kubectl exec --namespace <namespace> <pod-name> -- psql -c "
SELECT pid, state, wait_event_type, wait_event,
       now() - query_start AS duration, left(query, 120) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY duration DESC NULLS LAST;
"
```

On a **standby**, also check for a replay-blocking recovery conflict, which is the signature of the historical incident:

```bash
kubectl exec --namespace <namespace> <pod-name> -- psql -c "
SELECT pid, wait_event_type, wait_event, now() - query_start AS duration, left(query,120)
FROM pg_stat_activity
WHERE backend_type = 'client backend' AND wait_event_type IS NOT NULL;
"
# Replay actually frozen? restart_lsn / replay position should be advancing on the primary:
kubectl exec --namespace <namespace> services/<cluster_name>-rw -- psql -c "
SELECT application_name, state, replay_lsn, replay_lag FROM pg_stat_replication;
"
```

### Step 4: Inspect logs

```bash
kubectl logs --namespace <namespace> <pod-name> --tail=200
kubectl logs --namespace cnpg-system -l "app.kubernetes.io/name=cloudnative-pg" --tail=200
```

Look for collector errors, statement timeouts, or recovery-conflict / deadlock messages.

## Mitigation

1. **Unblock the stuck backend.** If a specific query is wedging the collector (or freezing replay on a standby), terminate it:

   ```bash
   kubectl exec --namespace <namespace> <pod-name> -- psql -c "SELECT pg_terminate_backend(<pid>);"
   ```

2. **Remove the offending instrumentation/custom query.** If the hang originates from a monitoring query (for example a ParadeDB `index_info` instrumentation that deadlocks on a replica), disable that instrumentation / custom query in the cluster's `.spec.monitoring` configuration until a fixed engine version is rolled out. Re-enable it after upgrading.

3. **Restart the instance as a last resort.** If the backend cannot be cleared, recycle the pod. Start with a **standby**, never the primary, to avoid an unnecessary failover:

   ```bash
   kubectl delete pod --namespace <namespace> <replica-pod-name>
   ```

4. **Confirm recovery.** The alert resolves once `cnpg_collector_up` is reported again for the pod. Verify the metric is flowing and that the previously-blinded replication/HA alerts are evaluating real data:

   ```bash
   kubectl exec --namespace <namespace> <pod-name> -- \
     curl -sS --max-time 5 http://localhost:9187/metrics | grep -E "cnpg_collector_up|cnpg_pg_replication_lag"
   ```

## Prevention

- Keep ParadeDB / CloudNativePG and any custom monitoring queries on versions known to be safe on **standbys**, not just primaries — exporter queries run on every instance, including replicas.
- Avoid expensive or lock-taking functions in `.spec.monitoring` custom queries and instrumentation; prefer cheap, read-only `pg_stat_*` reads.
- Treat this alert as a meta-monitor: when it fires, audit whether other replication/HA alerts should also have fired and were silenced.

## Quick Reference Commands

```bash
# Is the pod actually up and Ready?
kubectl get pods --namespace <namespace> -l "cnpg.io/podRole=instance" -o wide

# Is the metrics endpoint responding?
kubectl exec --namespace <namespace> <pod-name> -- curl -sS --max-time 5 http://localhost:9187/metrics | grep cnpg_collector_up

# What is the collector backend stuck on?
kubectl exec --namespace <namespace> <pod-name> -- psql -c "
SELECT pid, state, wait_event_type, wait_event, now() - query_start AS duration, left(query,120)
FROM pg_stat_activity WHERE state <> 'idle' ORDER BY duration DESC NULLS LAST;"

# Is replication actually frozen (run against the primary)?
kubectl exec --namespace <namespace> services/<cluster_name>-rw -- psql -c "
SELECT application_name, state, replay_lsn, replay_lag FROM pg_stat_replication;"

# Last-resort restart (standby first)
kubectl delete pod --namespace <namespace> <replica-pod-name>
```

## When to Escalate

- Contact support if:
  - The metrics endpoint stays unresponsive after terminating stuck backends.
  - `pg_stat_replication` on the primary shows replay is frozen for the affected standby (replication is stuck, not just unmonitored).
  - The collector wedges repeatedly after restart, or recurs across instances — this suggests a systemic instrumentation/engine bug that needs a version fix.
