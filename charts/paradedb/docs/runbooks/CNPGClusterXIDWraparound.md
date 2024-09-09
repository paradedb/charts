# CNPGClusterXIDWraparound

## Description

The `CNPGClusterXIDWraparoundWarning` and `CNPGClusterXIDWraparoundCritical` alerts fire when a database's transaction ID (`xid`) or multixact ID (`mxid`) age exceeds 1.5 billion or 2 billion, respectively. The `datname` label identifies the database and `age_kind` identifies which counter crossed the threshold.

PostgreSQL must freeze old transaction IDs before they approach their finite limit. Autovacuum normally handles this automatically, but a long-running transaction, prepared transaction, replication slot, or lagging standby can prevent the freeze horizon from advancing.

## Impact

- Increasing age means PostgreSQL is losing the remaining safety margin before wraparound protection activates.
- At roughly 2.1 billion transactions, PostgreSQL can refuse writes to prevent data loss.
- Recovery after write protection activates can require downtime and manual vacuuming.

## Diagnosis

Check both ages for every database:

```sql
SELECT datname,
       age(datfrozenxid) AS xid_age,
       mxid_age(datminmxid) AS mxid_age
FROM pg_database
ORDER BY GREATEST(age(datfrozenxid), mxid_age(datminmxid)) DESC;
```

Find the oldest relations in the affected database:

```sql
SELECT c.oid::regclass AS relation,
       age(c.relfrozenxid) AS xid_age,
       mxid_age(c.relminmxid) AS mxid_age,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS size
FROM pg_class AS c
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY GREATEST(age(c.relfrozenxid), mxid_age(c.relminmxid)) DESC
LIMIT 20;
```

Check for transactions and prepared transactions holding back the freeze horizon:

```sql
SELECT pid, state, backend_xmin, now() - xact_start AS transaction_age, query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;

SELECT gid, prepared, owner, database
FROM pg_prepared_xacts
ORDER BY prepared;
```

Also inspect `pg_replication_slots` for old `xmin` or `catalog_xmin` values and verify that all CloudNativePG replicas are healthy and replaying WAL.

## Mitigation

Remove the condition holding back the freeze horizon before running a manual vacuum:

- End abandoned long-running or idle-in-transaction sessions.
- Resolve orphaned prepared transactions with `COMMIT PREPARED` or `ROLLBACK PREPARED` after confirming the intended outcome.
- Restore an expected replication consumer or remove an abandoned logical slot after verifying it is no longer needed. Do not manually drop CloudNativePG-managed `_cnpg_` slots.
- Repair or replace a lagging CloudNativePG replica rather than disabling `hot_standby_feedback` globally.

After clearing the blocker, vacuum the oldest affected relations one at a time:

```sql
VACUUM (FREEZE, VERBOSE) <relation>;
```

Confirm that the database and relation ages are decreasing. Large relations can take significant time to vacuum, so continue monitoring available disk space and transaction ID age during recovery.

Do not increase `autovacuum_freeze_max_age` to silence the alert. It does not change PostgreSQL's wraparound limit and delays the automatic vacuum intended to prevent this condition.
