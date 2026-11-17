# CNPGClusterPhysicalReplicationLag

## Description

These alerts check replay latency and unreplayed WAL from `pg_stat_replication` on the upstream instance. `application_name` identifies the replica. Logical replication connections are excluded.

Each alert fires after five minutes above its threshold.

| Alert                                           | Condition                                                      |
| ----------------------------------------------- | -------------------------------------------------------------- |
| `CNPGClusterPhysicalReplicationLagWarning`      | Replay latency above 60 seconds and unreplayed WAL above zero  |
| `CNPGClusterPhysicalReplicationLagCritical`     | Replay latency above 600 seconds and unreplayed WAL above zero |
| `CNPGClusterPhysicalReplicationBacklogWarning`  | Replay backlog above 1 GiB                                     |
| `CNPGClusterPhysicalReplicationBacklogCritical` | Replay backlog above 10 GiB                                    |

For dedicated replica clusters, latency warns at 90 minutes and becomes critical at two hours. Backlog warns at 1 GiB and becomes critical at 10 GiB.

Replay latency (`cnpg_pg_stat_replication_replay_lag_seconds`) measures the time from flushing WAL on the primary to confirmation that the replica replayed it. It does not tell you how long the replica needs to catch up. CNPG reports zero once an idle measurement expires. If replay stalls, latency measurements can stop while the backlog grows. Check the backlog even when latency is low or missing.

Latency alerts only fire while that replica has unreplayed WAL, so a stale latency sample cannot trigger an alert after it catches up.

Disconnected replicas and replicas recovering only from archives have no sender row. Check connection and instance health as well.

## Impact

Queries to the `-r` and `-ro` endpoints may return stale data. Unreplayed WAL may already be stored durably on the replica. Backlog alone therefore does not tell you how much data a failover could lose. WAL that has not reached durable storage on the promoted replica may be lost.

## Diagnosis

Check replication status in the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/) or by running:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "SELECT * FROM pg_stat_replication;"
```

Check for:

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

## Connection status

The status indicator uses CNPG's default metrics: Connected, WAL pending, Disconnected, or Unknown. WAL pending means there is unreplayed WAL, which may be replaying normally. Missing metrics show as Unknown.

A dedicated replica cluster's primary can recover from archived WAL without a streaming connection, so it does not trigger disconnect warnings. Its streaming standbys need a WAL receiver. If they disconnect, check upstream reachability, authentication, replication slots, and PostgreSQL logs.

A small backlog can stall without triggering these alerts if it stays below the byte thresholds and reported latency stays low. CNPG's default metrics do not measure how long replay has stopped.

A standby with no WAL receiver for 15 minutes triggers a warning, even if sender metrics have disappeared. It may be recovering from archives, so this does not trigger a critical alert.
