# CNPGClusterPhysicalReplicationLag

## Description

For connected streaming replicas, `CNPGClusterPhysicalReplicationLagWarning` and `CNPGClusterPhysicalReplicationLagCritical` use `cnpg_pg_stat_replication_replay_lag_seconds`, the primary's measurement of time taken to acknowledge recent WAL replay:

- **Warning**: above 60 seconds for five minutes.
- **Critical**: above 600 seconds for five minutes.

`CNPGClusterPhysicalReplicationBacklogWarning` and `CNPGClusterPhysicalReplicationBacklogCritical` separately monitor `cnpg_pg_stat_replication_replay_diff_bytes`:

- **Warning**: above 1 GiB of unreplayed WAL for five minutes.
- **Critical**: above 10 GiB of unreplayed WAL for five minutes.

Sender metrics are exported on the primary, with the standby named by `application_name`. Backlog alerts map that label to the standby `pod`. CNPG's `streaming_replica` user distinguishes physical connections from logical ones.

Replay latency measures acknowledgment of recent WAL, not catch-up time. PostgreSQL makes it NULL after the standby catches up and the connection becomes idle; CNPG exports that NULL as zero. A stalled standby can have substantial backlog despite low or unavailable latency, so inspect both measurements. Missing connection metrics are not proof of health; also check HA and missing-exporter alerts.

For archive-only instances in replica mode without a corresponding sender metric, the chart retains its existing `cnpg_pg_replication_lag` check. This is a transaction-age heuristic: [CNPG's SQL](https://github.com/cloudnative-pg/cloudnative-pg/blob/v1.30.1/config/manager/default-monitoring.yaml#L110) returns the age of the last replayed transaction commit/abort whenever received and replayed WAL positions differ. During indexing without other commits it can show hours of apparent lag despite fast replay. Confirm WAL positions and progress before treating it as a replication failure. MCC applies its separate 90/120-minute allowances to dedicated replica clusters.

## Impact

A genuine replay backlog can make read-replica queries stale. Failover data-loss risk depends on which WAL has reached durable storage on the promoted standby, not solely on replay latency or unreplayed bytes. WAL received and flushed but not yet replayed can still be recovered.

## Diagnosis

Check replication status in the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/) or by running:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "SELECT application_name, state, replay_lag, pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_backlog_bytes, pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) AS unflushed_bytes FROM pg_stat_replication;"
```

High physical replication lag can be caused by a number of factors:

- Network congestion on the node interface, or insufficient bandwidth between the primary and its replicas. Inspect the network interface statistics using the `Kubernetes Cluster` section of the Grafana dashboard.

- High CPU or memory load on the primary or the replicas, or disk I/O bottlenecks on the replicas. Inspect the CPU, memory and disk I/O statistics using the Grafana dashboard, or run:

```bash
kubectl top -n <namespace> pods -l "cnpg.io/podRole=instance"
```

- Long-running transactions generating excessive changes. Inspect the `Stat Activity` section of the Grafana dashboard, or run:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '5 minutes'
ORDER BY duration DESC;
"
```

- Suboptimal PostgreSQL configuration, for example too few `max_wal_senders`. Inspect the `PostgreSQL Parameters` section of the Grafana dashboard, or run:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "SHOW max_wal_senders; SHOW wal_compression;"
```

## Mitigation

- Terminate long-running transactions that generate excessive changes:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'active'
  AND now() - query_start > interval '30 minutes'
  AND query NOT LIKE '%autovacuum%';
"
```

Terminating a backend is disruptive, and a query long enough to cause replication lag has usually tripped [`PostgreSQLLongRunningQueriesWarning`](./PostgreSQLLongRunningQueriesWarning.md) as well. That runbook covers which queries are safe to cancel and why `pg_cancel_backend` is preferred over terminating.

- Increase the memory and CPU resources of the instances under heavy load. This can be done by setting `cluster.resources.requests` and `cluster.resources.limits` in your Helm values. Set both `requests` and `limits` to the same value to achieve QoS Guaranteed. This will require a restart of the CloudNativePG cluster instances and a primary switchover, which will cause a brief service disruption.

- Enable `wal_compression` by setting the `cluster.postgresql.parameters.wal_compression` parameter to `on`. Doing so will reduce the size of the WAL files and can help reduce replication lag in a congested network. Changing `wal_compression` does not require a restart of the CloudNativePG cluster.

- If the cluster has nine or more instances, ensure that the `cluster.postgresql.parameters.max_wal_senders` parameter is set to a value greater than or equal to the total number of instances in your cluster. The default of 10 is usually sufficient.

- Increase IOPS or throughput of the storage used by the cluster to alleviate disk I/O bottlenecks. This requires creating a new storage class with higher IOPS/throughput and rebuilding cluster instances and their PVCs one by one using the new storage class. This is a slow process that will also affect the cluster's availability.

If you decide to go this route, start by creating a new storage class. Storage classes are immutable, so you cannot change the storage class of existing Persistent Volume Claims (PVCs). Then rebuild the instances onto it, starting with a standby rather than the primary.

> [!IMPORTANT]
> Recreate pods one at a time, to avoid increasing the load on the primary instance. Before deleting, verify that:
>
> - You are connected to the correct cluster.
> - You are deleting the correct pod.
> - You are not deleting the active primary instance.

```bash
kubectl delete -n <namespace> pod/<pod-name> pvc/<pod-name> pvc/<pod-name>-wal
```
