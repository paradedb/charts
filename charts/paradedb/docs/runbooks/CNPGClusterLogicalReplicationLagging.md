# CNPGClusterLogicalReplicationLagging

## Description

The `CNPGClusterLogicalReplicationLagging` and `CNPGClusterLogicalReplicationLaggingCritical` alerts measure message receipt age for each database/subscription pair.

- **Warning level**: receipt age exceeds 60 seconds for 5 minutes
- **Critical level**: receipt age exceeds 300 seconds for 2 minutes

Both use `cnpg_pg_stat_subscription_receipt_lag_seconds`, with `time() - cnpg_pg_stat_subscription_last_msg_receipt_time` as a fallback for exporters without the derived metric. Receipt age measures transport activity, not committed apply progress.

The legacy `cnpg_pg_stat_subscription_apply_lag_seconds` measures the age of `latest_end_time`, and `cnpg_pg_stat_subscription_buffered_lag_bytes` measures the nonnegative received-versus-reported WAL position gap. They remain available for dashboard compatibility, but neither establishes committed apply delay or unapplied backlog. They do not trigger these alerts.

## Impact

The cluster remains operational, but queries against the subscriber return stale data and the divergence from the publisher grows for as long as the lag persists. The publisher also retains WAL for the subscription's replication slot, so a sustained lag consumes disk space there.

## Diagnosis

- Connect to the affected database and inspect receipt activity:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -d <database> -c "
SELECT
    s.subname,
    s.subenabled AS enabled,
    EXTRACT(EPOCH FROM (NOW() - ss.last_msg_receipt_time)) AS receipt_lag_seconds,
    EXTRACT(EPOCH FROM (NOW() - ss.latest_end_time)) AS reported_position_age_seconds,
    COALESCE(pg_wal_lsn_diff(ss.received_lsn, ss.latest_end_lsn), 0) AS received_reported_gap_bytes
FROM pg_subscription s
LEFT JOIN pg_stat_subscription ss ON s.oid = ss.subid
WHERE s.subdbid = (SELECT oid FROM pg_database WHERE datname = current_database());
"
```

- For receipt lag, check connectivity to the publisher:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- nc -zv <publisher-host> 5432
```

- If separate investigation indicates slow apply, check resource usage and long-running queries on the subscriber:

```bash
kubectl top -n <namespace> pods -l "cnpg.io/podRole=instance"
```

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '5 minutes'
ORDER BY duration DESC;
"
```

- Verify the subscriber has enough worker processes. `max_worker_processes` must be at least `max_parallel_workers` plus `max_logical_replication_workers`:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
SHOW max_worker_processes; SHOW max_logical_replication_workers; SHOW max_parallel_workers;
"
```

- Check how much WAL the publisher is retaining for the subscription:

```bash
kubectl exec -n <namespace> -it services/<publisher-cluster-name>-rw -- psql -c "
SELECT slot_name, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots WHERE slot_type = 'logical';
"
```

- Review the lag graphs over time in the `Logical Replication` section of the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/) to establish whether the lag is stable, growing, or correlated with workload spikes.

## Mitigation

For receipt lag:

- Check for network congestion or throttling between the two clusters. Where possible, run the publisher and subscriber in the same region.

- Tune `cluster.postgresql.parameters.wal_receiver_status_interval` and `wal_sender_timeout` so that a slow link is not mistaken for a dead one.

For independently confirmed apply delays:

- Increase the memory and CPU resources of the subscriber by setting `cluster.resources.requests` and `cluster.resources.limits` in your Helm values.

- Increase IOPS or throughput of the subscriber's storage if disk I/O is the bottleneck.

- Raise `cluster.postgresql.parameters.max_wal_size` and `wal_buffers` on the subscriber to reduce checkpoint pressure while a backlog is being applied.

For a sustained high transaction volume:

- Break large transactions into smaller ones on the publisher, and prefer `COPY` over large batches of individual `INSERT` statements.

- Replicate less by narrowing the publication or adding row filters, so the subscriber has less to apply:

```sql
ALTER PUBLICATION <publication> ADD TABLE <table> WHERE (<condition>);
```

If the subscription is not lagging but stalled entirely, see the [`CNPGClusterLogicalReplicationStopped`](./CNPGClusterLogicalReplicationStopped.md) runbook.
