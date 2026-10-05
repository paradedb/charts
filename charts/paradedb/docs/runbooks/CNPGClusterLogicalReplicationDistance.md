# CNPGClusterLogicalReplicationDistance

## Description

These alerts report the subscriber's `received_lsn` minus `latest_end_lsn`.
Warning fires above 1 GiB for five minutes; critical fires above 4 GiB for two
minutes. Labels identify the pod, database, and subscription.

## Impact

A large WAL-position gap warrants investigation but does not measure unapplied
work or committed apply progress. Missing worker metrics cannot trigger these
alerts; check worker health separately.

## Diagnosis

Inspect the subscription on the subscriber database:

```sql
SELECT subname, pid, received_lsn, latest_end_lsn,
       last_msg_receipt_time, latest_end_time,
       pg_wal_lsn_diff(received_lsn, latest_end_lsn) AS position_gap_bytes
FROM pg_stat_subscription;
```

Check receipt age and worker health, and use the
[logical replication error runbook](CNPGClusterLogicalReplicationErrors.md) to
inspect apply/sync errors and subscriber logs.

## Mitigation

Address any confirmed connection, worker, or apply errors found during diagnosis.
Do not skip transactions or resynchronize a subscription based on this position
gap alone.
