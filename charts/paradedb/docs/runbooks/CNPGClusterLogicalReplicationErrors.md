# CNPGClusterLogicalReplicationErrors

## Description

The `CNPGClusterLogicalReplicationErrors` and `CNPGClusterLogicalReplicationErrorsCritical` alerts are triggered when a logical replication subscription reports errors. These come in two kinds:

- **Apply errors**: raised when applying changes received from the publisher
- **Sync errors**: raised during the initial table synchronization

- **Warning level**: any error in the last 5 minutes
- **Critical level**: 5 or more errors in the last 5 minutes

## Impact

PostgreSQL stops applying changes when it hits a conflict and retries the same transaction, so the subscription makes no progress until the conflict is resolved. The subscriber's data diverges from the publisher, and the publisher retains WAL for the subscription's replication slot in the meantime.

## Diagnosis

- Confirm which subscription is failing and in which phase:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<subscriber-cluster-name>-rw -- psql -c "
SELECT
    s.subname,
    s.subenabled AS enabled,
    COALESCE(sss.apply_error_count, 0) AS apply_error_count,
    COALESCE(sss.sync_error_count, 0) AS sync_error_count,
    sss.stats_reset
FROM pg_subscription s
LEFT JOIN pg_stat_subscription_stats sss ON s.oid = sss.subid;
"
```

- Find the error itself in the subscriber logs. The statistics counters say that something failed, but only the logs say what:

```bash
kubectl logs --namespace <namespace> pod/<instance-pod-name> --tail=200 | grep -i "logical replication\|conflict\|duplicate key"
```

A conflict is logged with the table and key involved:

```text
ERROR: duplicate key value violates unique constraint "test_pkey"
DETAIL: Key (c)=(1) already exists.
CONTEXT: processing remote data for replication origin "pg_16395" during "INSERT"
for replication target relation "public.test" in transaction 725 finished at 0/14C0378
```

Common causes, in rough order of frequency:

- Rows written directly on the subscriber that collide with replicated rows, giving unique or foreign key violations
- Schema drift between publisher and subscriber, giving missing column or type errors
- A table that does not exist on the subscriber, which fails during initial sync
- Insufficient privileges for the subscription owner on the target tables

- For a sync error, check which tables never reached a ready state:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<subscriber-cluster-name>-rw -- psql -c "
SELECT srrelid::regclass AS table_name, srsubstate AS state
FROM pg_subscription_rel WHERE srsubstate NOT IN ('r', 's');
"
```

- Compare the definitions of the affected table on both clusters to rule out schema drift:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<publisher-cluster-name>-rw -- psql -c "\d+ <table>"
kubectl exec --namespace <namespace> --stdin --tty services/<subscriber-cluster-name>-rw -- psql -c "\d+ <table>"
```

## Mitigation

### Resolve the Conflict

This is the usual path. Remove or correct the conflicting row on the subscriber, and replication retries the transaction and resumes on its own — the transaction does not need to be skipped manually:

```sql
DELETE FROM <table> WHERE <primary-key> = <conflicting-value>;
```

Only delete the subscriber's row if the publisher's version should win.

For schema drift, alter the subscriber's table to match the publisher, or create the missing table, then refresh the subscription:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<subscriber-cluster-name>-rw -- psql -c "ALTER SUBSCRIPTION <subscription> REFRESH PUBLICATION;"
```

### Skip the Transaction

If the subscriber's version of the data is the one to keep, skip the failing transaction using the LSN from the `CONTEXT` line in the log:

```sql
ALTER SUBSCRIPTION <subscription> SKIP (lsn = '0/14C0378');
```

> [!IMPORTANT]
> Skipping discards the publisher's transaction permanently and leaves the two clusters divergent. Record what was skipped and why.

### Resynchronize

If there are many conflicts, or the subscriber's state is unknown, re-copy the affected tables:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<subscriber-cluster-name>-rw -- psql -c "
ALTER SUBSCRIPTION <subscription> REFRESH PUBLICATION WITH (copy_data = true);
"
```

This can take a long time on large tables. Treat it as a last resort.

The most effective prevention is not writing to replicated tables on the subscriber, and applying schema changes to the subscriber before the publisher.
