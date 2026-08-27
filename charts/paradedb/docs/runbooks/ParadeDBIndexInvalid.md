# ParadeDBIndexInvalid

## Description

The `ParadeDBIndexInvalid` alert is triggered when PostgreSQL reports that a ParadeDB index on the cluster primary is invalid or not ready for inserts.

This commonly happens when `CREATE INDEX CONCURRENTLY` fails or is cancelled. PostgreSQL leaves the incomplete index behind, consuming storage even though the planner will not use it. Search queries can silently fall back to a sequential scan and become much slower without returning an application error.

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
WHERE am.amname = 'paradedb'
  AND (NOT i.indisvalid OR NOT i.indisready)
ORDER BY n.nspname, c.relname;
"
```

Check PostgreSQL logs and recent deployment or maintenance activity to determine why the index build failed. Confirm that another index build is not still in progress before changing the index.

## Mitigation

PostgreSQL cannot make a failed concurrent index valid after the fact. Drop the invalid index and recreate it:

```sql
DROP INDEX CONCURRENTLY <schema>.<index_name>;
CREATE INDEX CONCURRENTLY <index_name>
ON <schema>.<table_name>
USING paradedb (...)
WITH (key_field = '<key_column>');
```

Recover the exact original definition with `pg_get_indexdef(indexrelid)` before dropping the index. Schedule the rebuild with enough time and capacity to finish, and do not cancel it unless leaving another invalid index is acceptable.

After recreation, confirm both `indisvalid` and `indisready` are true and that the alert clears.
