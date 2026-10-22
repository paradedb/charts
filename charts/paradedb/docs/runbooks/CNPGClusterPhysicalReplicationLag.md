# CNPGClusterPhysicalReplicationLag

## Description

Physical replication alerts use replay latency and WAL replay backlog. Both metrics come from the upstream's `pg_stat_replication` view. The alerts use `application_name` to identify the receiving replica and exclude logical replication connections.

Latency and backlog thresholds must hold for five minutes.

| Alert | Condition |
| --- | --- |
| `CNPGClusterPhysicalReplicationLagWarning` | Replay latency above 60 seconds and unreplayed WAL above zero |
| `CNPGClusterPhysicalReplicationLagCritical` | Replay latency above 600 seconds and unreplayed WAL above zero |
| `CNPGClusterPhysicalReplicationBacklogWarning` | Replay backlog above 1 GiB |
| `CNPGClusterPhysicalReplicationBacklogCritical` | Replay backlog above 10 GiB |

Dedicated replica clusters retain their 90-minute warning and two-hour critical latency thresholds. Their byte-backlog thresholds are unchanged.

Replay latency measures how long recent WAL took to be replayed and acknowledged. It does not estimate catch-up time. CNPG reports zero after an idle latency measurement expires. A stalled replica can also stop producing new measurements while its backlog grows, so the byte-backlog alerts stay active even when latency is low or missing.

The latency alerts require unreplayed WAL on the same replica. An old latency sample cannot fire an alert after that replica has caught up. The old `cnpg_pg_replication_lag` transaction-age metric is not used.

Disconnected replicas and archive-only recovery have no sender row. Missing connections and unavailable instances need separate health monitoring.

## Impact

Physical replication lag can cause the cluster replicas to become out of sync. Queries to the `-r` and `-ro` endpoints may return stale data. Unreplayed WAL may already be durable on the replica, so replay backlog alone does not measure failover data-loss risk. WAL that has not reached durable storage on the promoted replica may be lost.

## Diagnosis

Check replication status in the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/) or by running:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "SELECT * FROM pg_stat_replication;"
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

## Replay stalls and disconnects

The status indicator shows Connected, WAL pending, Stalled, Disconnected, or Unknown. Connected means the receiver is connected with no observed pending WAL. It is not a guarantee of data freshness. The two main graphs remain replay latency and WAL replay backlog.

A stalled replica has pending WAL and no change in its replay position for five minutes. This catches small stalled backlogs even when the recent replay-latency measurement is low. Warning and critical alerts use five-minute and fifteen-minute no-progress windows, followed by a one-minute hold. Dedicated replica clusters retain their 90-minute warning and two-hour critical allowance for stalls as well as latency. The status indicator still shows a five-minute stall so operators can see it before the alert threshold.

A replica with no WAL receiver warns after five minutes and alerts critically after fifteen minutes. This describes the streaming connection, not data loss. The replica may still be replaying archived WAL. These thresholds also apply to dedicated replicas.

The extra query adds only instance-wide replay position and locally received pending bytes. Recovery and WAL receiver health come from CNPG's default queries, which must remain enabled. Pending work uses upstream replay backlog when available and falls back to locally received pending bytes. That fallback cannot see WAL that the upstream has not sent. No heartbeat or transaction-age metric is used.

Missing position samples do not establish a stall. Missing receiver telemetry does not establish a disconnect. Keep the existing exporter, instance-health, and HA alerts enabled to cover missing telemetry. A new replica needs enough samples to fill the no-progress window before a stall can fire.

For a stalled replica, compare the replay position over time and check recovery conflicts, disk latency, replay pause settings, and the PostgreSQL logs. If the receiver is disconnected, check upstream reachability, authentication, replication slots, and archive recovery before restarting anything.
