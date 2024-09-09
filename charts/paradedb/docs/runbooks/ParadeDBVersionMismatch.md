# ParadeDBVersionMismatch

## Description

The alert fires when the `pg_search` extension catalog version on the writable primary differs from the default extension version shipped in the deployed image for 15 minutes.

## Impact

Calls into `pg_search` can fail. Index detail queries are disabled while the versions disagree; catalog-only index health metrics remain available.

## Diagnosis

Compare the catalog and image versions in each affected database without calling extension functions:

```sql
SELECT e.extversion AS installed_version, a.default_version AS expected_version
FROM pg_extension e
JOIN pg_available_extensions a ON a.name = e.extname
WHERE e.extname = 'pg_search';
```

Check the alert's database and version labels and confirm that CloudNativePG is running the intended image. An image upgrade without a corresponding extension update is a common cause.

## Mitigation

If the image is correct and the catalog is older, update the extension in each affected database:

```sql
ALTER EXTENSION pg_search UPDATE;
```

If the image is older than the catalog, complete the intended image rollout instead of downgrading the catalog. Confirm that the versions agree and `cnpg_paradedb_version_match` returns `1` after reconciliation.
