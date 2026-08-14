# CNPGClusterXIDWraparound

## Description

The `CNPGClusterXIDWraparoundWarning` and `CNPGClusterXIDWraparoundCritical` alerts are triggered when a database's transaction ID age approaches the point at which PostgreSQL refuses to start new transactions.

- **Warning level**: age exceeds 1,000,000,000
- **Critical level**: age exceeds 1,500,000,000

Two counters are covered, and either one crossing the threshold fires the alert:

- **`xid`** — `age(datfrozenxid)`, the ordinary transaction ID age, from `cnpg_pg_database_xid_age`
- **`mxid`** — `mxid_age(datminmxid)`, the multixact ID age, from `cnpg_pg_database_mxid_age`

Multixact IDs are allocated when several transactions hold row-level locks on the same row, so a workload with heavy `SELECT ... FOR SHARE`, foreign key checks, or subtransactions can age its multixact counter far faster than its transaction counter. The consequence of exhausting either is the same, and the multixact case is the one more often missed.

The `age_kind` label on the alert says which counter tripped, and `datname` says which database.

## Impact

PostgreSQL stops accepting write transactions at roughly 2.1 billion, refusing them with:

```
database is not accepting commands to avoid wraparound data loss in database "<name>"
```

This is a protective stop, not corruption, but recovering from it requires downtime: the database has to be vacuumed with no writes in flight, and a `VACUUM FREEZE` over a large table is not quick.

The alert thresholds are set well before that point on purpose. At 1 billion there are typically weeks of headroom and the fix is to unblock autovacuum. The condition is entirely silent up to the moment it stops the database, so the lead time is the whole value of the alert.

## Diagnosis

Both counters, per database, highest first:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
  SELECT datname,
         age(datfrozenxid) AS xid_age,
         mxid_age(datminmxid) AS mxid_age
  FROM pg_database
  ORDER BY GREATEST(age(datfrozenxid), mxid_age(datminmxid)) DESC;"
```

A database's age is the age of its oldest table, so find the tables holding it back:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
  SELECT c.oid::regclass AS relation,
         age(c.relfrozenxid) AS xid_age,
         pg_size_pretty(pg_total_relation_size(c.oid)) AS size
  FROM pg_class c
  WHERE c.relkind IN ('r', 'm', 't')
  ORDER BY age(c.relfrozenxid) DESC
  LIMIT 20;"
```

If autovacuum is running and the age still climbs, something is pinning the horizon. There are four usual causes, and all four are visible:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
  SELECT pid, state, backend_xmin, now() - xact_start AS xact_duration, left(query, 60) AS query
  FROM pg_stat_activity
  WHERE xact_start IS NOT NULL
  ORDER BY xact_start
  LIMIT 10;"
```

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
  SELECT gid, prepared, owner, database FROM pg_prepared_xacts ORDER BY prepared;"
```

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
  SELECT slot_name, slot_type, active, xmin, catalog_xmin FROM pg_replication_slots;"
```

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
  SELECT name, setting FROM pg_settings
  WHERE name IN ('autovacuum', 'autovacuum_freeze_max_age', 'autovacuum_multixact_freeze_max_age',
                 'vacuum_freeze_table_age', 'hot_standby_feedback');"
```

In order of how often they are the answer: a long-running or idle-in-transaction session, an orphaned prepared transaction, a replication slot that is inactive or badly behind, and a standby with `hot_standby_feedback = on` holding the primary's horizon.

Check whether autovacuum is keeping up at all:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
  SELECT relname, last_autovacuum, autovacuum_count, n_dead_tup
  FROM pg_stat_user_tables
  ORDER BY n_dead_tup DESC
  LIMIT 10;"
```

## Mitigation

Clear the blocker first. Freezing cannot advance past a horizon something else is holding, so a `VACUUM FREEZE` run before that is wasted work.

- **Long-running transaction**: end it, or `SELECT pg_terminate_backend(<pid>);` if it is abandoned. Idle-in-transaction sessions are the common case and are usually an application that opened a transaction and did not commit.
- **Prepared transaction**: `ROLLBACK PREPARED '<gid>';` — an orphaned entry in `pg_prepared_xacts` holds the horizon indefinitely and nothing times it out.
- **Replication slot**: reconnect the consumer, or drop the slot with `SELECT pg_drop_replication_slot('<slot_name>');` if it belongs to a subscriber that is gone for good. Dropping a slot that is still in use breaks that replica, so confirm before dropping. See the [`CNPGClusterLogicalReplicationStopped`](./CNPGClusterLogicalReplicationStopped.md) runbook where the slot belongs to a subscription.
- **`hot_standby_feedback`**: expected on a cluster with replicas serving reads. It only becomes the cause when a standby is stuck, so treat a stuck standby as the problem rather than turning the setting off.

With the horizon free, autovacuum normally catches up on its own — `autovacuum_freeze_max_age` (200 million by default) forces a wraparound vacuum long before the thresholds here. If it does not, freeze the worst tables by hand, one at a time, since each holds a lock and reads the whole table:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "VACUUM (FREEZE, VERBOSE) <relation>;"
```

Then confirm the age is falling with the first query above. It will not drop immediately: the database's age only moves once every table below it has been frozen.

> [!IMPORTANT]
> Do not raise `autovacuum_freeze_max_age` to quiet the alert. It buys no headroom — the hard stop is fixed at roughly 2.1 billion regardless — and it removes the forced vacuum that would otherwise have prevented this.

If the database has already stopped accepting commands, it has to be started in single-user mode and vacuumed with no other connections. That is an outage, and it is why these alerts fire a billion transactions early.
