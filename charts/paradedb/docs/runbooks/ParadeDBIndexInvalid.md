# ParadeDBIndexInvalid

## Description

The `ParadeDBIndexInvalid` alert is triggered when the cluster primary reports one or more invalid or not-ready ParadeDB indexes for five minutes. The notification reports their total across databases; standby copies are not counted again.

This commonly happens when `CREATE INDEX CONCURRENTLY` or `REINDEX CONCURRENTLY` fails or is cancelled. PostgreSQL leaves the incomplete index behind, consuming storage even though the planner will not use it. Queries can silently fall back to a sequential scan and become much slower without returning an application error.

The catalog-only `cnpg_paradedb_invalid_indexes_count` metric reports the count per database, including zero. Indexes reported as actively building in `pg_stat_progress_create_index` are excluded, including builds waiting for locks or validation. Failed or cancelled builds are counted once their progress entry disappears. `cnpg_paradedb_index_health_is_valid` and `cnpg_paradedb_index_health_is_ready` identify the individual indexes. MCC Customer Overview shows the cluster total under **ParadeDB Indexes**. These metrics do not open index storage.

## Impact

- An index with `indisvalid = false` is not available to the query planner.
- An index with `indisready = false` does not receive inserts and can fall behind its table.
- The incomplete index continues to occupy storage until it is dropped.
- Queries that normally use the index may consume substantially more CPU and take much longer.

## Diagnosis

Inspect the index state on the primary:

```bash
kubectl exec -n <namespace> -it services/paradedb-rw -- psql -c "
SELECT n.nspname AS schema,
       t.relname AS table_name,
       c.relname AS index_name,
       i.indisvalid,
       i.indisready
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_index i ON i.indexrelid = c.oid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_am am ON am.oid = c.relam
WHERE am.amname IN ('paradedb', 'bm25')
  AND (NOT i.indisvalid OR NOT i.indisready)
ORDER BY n.nspname, c.relname;
"
```

Check PostgreSQL logs and recent deployment or maintenance activity to determine why the index build failed. Confirm that another index build is not still in progress before changing the index.

## Mitigation

For a failed concurrent reindex, first check whether the original or replacement index is already valid. An invalid `_ccnew` leftover may only need removal; do not drop the valid index or automatically start another rebuild.

If the intended index itself is missing or unusable, recover its exact definition and plan a rebuild. For example:

```sql
DROP INDEX CONCURRENTLY <schema>.<index_name>;
CREATE INDEX CONCURRENTLY <index_name>
ON <schema>.<table_name>
USING paradedb (...)
WITH (key_field = '<key_column>');
```

Recover the exact original definition with `pg_get_indexdef(indexrelid)` before dropping the index. Schedule the rebuild with enough time and capacity to finish, and do not cancel it unless leaving another invalid index is acceptable.

After recreation, confirm both `indisvalid` and `indisready` are true and that the alert clears.
