# ParadeDBVersionMismatch

## Description

The `ParadeDBVersionMismatch` alert fires when the `pg_search` extension version recorded in PostgreSQL does not match the ParadeDB version declared by the Helm release for at least 15 minutes.

ParadeDB loads native code into PostgreSQL. If the extension catalog and the installed binary disagree, calls into `pg_search` can cause errors. ParadeDB monitoring queries that use extension functions are therefore disabled until the versions match, leaving index health and telemetry unavailable.

## Impact

- Queries that invoke `pg_search` can return errors.
- ParadeDB index health, size, segment, and document metrics stop being collected intentionally.
- Search traffic may fail or be disrupted until the catalog and binary versions agree.

## Diagnosis

Compare the version in the loaded ParadeDB binary with the version recorded in PostgreSQL's extension catalog:

```sql
SELECT * FROM paradedb.version_info();
SELECT extversion FROM pg_extension WHERE extname = 'pg_search';
```

`paradedb.version_info()` reports the version in the installed binary, while `pg_extension.extversion` reports the version PostgreSQL's catalog expects. If they do not match, binary/catalog version skew is causing the alert.

The most common cause is upgrading the ParadeDB binary without subsequently running `ALTER EXTENSION pg_search UPDATE` in the database, leaving PostgreSQL's extension catalog and SQL objects on the older version.

Also compare both values with the alert's `expected_version` label and the version configured in the Helm release. Inspect the images CloudNativePG is running:

```bash
kubectl get pods -n <namespace> -l cnpg.io/cluster=<cluster> \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[?(@.name=="postgres")].image}{"\n"}{end}'
```

## Mitigation

If `paradedb.version_info()` reports the intended binary version but `pg_extension.extversion` is older, update the extension in every database where `pg_search` is installed:

```sql
ALTER EXTENSION pg_search UPDATE TO '<binary_version>';
```

If `pg_extension.extversion` is newer than `paradedb.version_info()`, the binary upgrade has not completed. Reconcile the deployed image and restart PostgreSQL rather than altering the catalog backward.

Ensure `version.paradedb`, the deployed ParadeDB image, and the managed `pg_search` extension version all refer to the same release. If `cluster.imageName` or `cluster.imageCatalogRef` overrides the default image, verify that the override contains the version declared by `version.paradedb`.

Allow CloudNativePG to complete any rolling restart and extension reconciliation. Then rerun both diagnosis queries, confirm their versions match, and verify that every database reports `cnpg_paradedb_version_match` as `1`.
