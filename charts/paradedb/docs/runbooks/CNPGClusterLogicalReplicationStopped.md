# CNPGClusterLogicalReplicationStopped

## Description

The `CNPGClusterLogicalReplicationStopped` and `CNPGClusterLogicalReplicationStoppedCritical` alerts are triggered when a logical replication subscription is not actively replicating data. This happens in one of two ways:

- The subscription has been explicitly disabled (`subenabled = false`)
- The subscription is enabled but has no worker process while data is still pending

- **Warning level**: the subscription has been stopped for 5 minutes
- **Critical level**: the subscription has been stopped for 15 minutes

## Impact

The subscriber receives no updates from the publisher and its data becomes increasingly stale. The publisher retains WAL for the subscription's replication slot for as long as the subscription is stopped, so its disk usage grows. If the slot is dropped or the retained WAL is discarded before the subscription catches up, recovering will require a full resynchronization.

## Diagnosis

- Determine which of the two conditions applies:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<subscriber-cluster-name>-rw -- psql -c "
SELECT
    s.subname,
    s.subenabled AS enabled,
    ss.pid IS NOT NULL AS has_worker,
    COALESCE(pg_wal_lsn_diff(ss.received_lsn, ss.latest_end_lsn), 0) AS pending_bytes
FROM pg_subscription s
LEFT JOIN pg_stat_subscription ss ON s.oid = ss.subid;
"
```

- Check the subscriber logs for the reason the worker exited:

```bash
kubectl logs --namespace <namespace> pod/<instance-pod-name> --tail=200 | grep -i "subscription\|replication\|worker"
```

An apply error will stop the worker and keep it from restarting. If the logs show constraint violations or similar conflicts, follow the [`CNPGClusterLogicalReplicationErrors`](./CNPGClusterLogicalReplicationErrors.md) runbook instead.

- Confirm the publisher is reachable and still has the publication and slot:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<publisher-cluster-name>-rw -- psql -c "
SELECT pubname FROM pg_publication;
SELECT slot_name, active, pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots WHERE slot_type = 'logical';
"
```

- Check the worker limits on the subscriber. A subscription cannot start a worker if the pool is exhausted:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<subscriber-cluster-name>-rw -- psql -c "
SHOW max_logical_replication_workers;
SHOW max_worker_processes;
SELECT count(*) FROM pg_stat_activity WHERE backend_type = 'logical replication worker';
"
```

## Mitigation

### Disabled Subscription

Confirm the subscription was not disabled deliberately, for example during a maintenance window, then re-enable it:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<subscriber-cluster-name>-rw -- psql -c "ALTER SUBSCRIPTION <subscription> ENABLE;"
```

### Stuck Subscription

- If the worker pool is exhausted, raise `cluster.postgresql.parameters.max_logical_replication_workers` and `max_worker_processes` in your Helm values. `max_worker_processes` must be at least `max_parallel_workers` plus `max_logical_replication_workers`, and changing it requires a restart of the cluster instances.

- If a long-running transaction on the subscriber is blocking the apply worker, terminate it:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<subscriber-cluster-name>-rw -- psql -c "
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '10 minutes';
"
```

- Force the subscription to restart its worker:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<subscriber-cluster-name>-rw -- psql -c "
ALTER SUBSCRIPTION <subscription> DISABLE;
ALTER SUBSCRIPTION <subscription> ENABLE;
"
```

### Missing WAL on the Publisher

If the publisher has already discarded the WAL the subscription needs, or its slot no longer exists, the subscription cannot catch up and the tables must be copied again:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<subscriber-cluster-name>-rw -- psql -c "
ALTER SUBSCRIPTION <subscription> REFRESH PUBLICATION WITH (copy_data = true);
"
```

> [!IMPORTANT]
> A refresh with `copy_data = true` re-copies the affected tables and can take a long time on large datasets. Prefer it only once the causes above have been ruled out.

To avoid a recurrence, raise `cluster.postgresql.parameters.max_slot_wal_keep_size` on the publisher so that slots are not invalidated during a short outage. Note that this trades disk space on the publisher for tolerance to subscriber downtime.
