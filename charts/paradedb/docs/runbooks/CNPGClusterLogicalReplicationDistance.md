# CNPGClusterLogicalReplicationDistance

These alerts report the difference between the subscriber's `received_lsn` and
`latest_end_lsn`. Warning fires above 1 GiB for five minutes; critical fires above
4 GiB for two minutes, matching MCC's distance thresholds. Labels retain the pod,
database, and subscription so same-named subscriptions remain distinct.

This is a received-versus-reported WAL-position gap, not the amount of unapplied
work or a measurement of committed apply progress. Missing worker metrics cannot
trigger these alerts; worker-down detection handles that case separately.

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
inspect apply/sync errors and subscriber logs. Do not skip transactions or
resynchronize a subscription based on this position gap alone.
