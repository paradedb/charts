# CNPGClusterLogicalReplicationApplyErrors

## Meaning

The `CNPGClusterLogicalReplicationApplyErrors` alert indicates that a CloudNativePG cluster with a logical replication subscription has experienced one or more errors while attempting to apply changes from the publisher. This is detected by an increase in the `apply_error_count` from `pg_stat_subscription_stats` over the last 5 minutes.

Apply errors occur when the subscriber receives data from the publisher but cannot successfully apply those changes to the local database. Common causes include:

* **Data conflicts**: Constraint violations, unique key conflicts, or check constraint failures.
* **Permission issues**: The subscription user lacks necessary privileges on target tables.
* **Schema mismatches**: Column type differences, missing columns, or incompatible table structures.
* **Row Level Security (RLS) conflicts**: RLS policies preventing data insertion/modification.
* **Trigger conflicts**: Triggers on subscriber tables that interfere with replicated operations.
* **Foreign key constraint violations**: Referential integrity conflicts with existing data.

## Impact

The logical replication subscription will stop processing changes once errors occur, leading to increasing data divergence between publisher and subscriber. Applications querying the subscriber will receive stale data that may not reflect recent changes on the publisher.

## Diagnosis

1. Connect via psql to the subscriber and check for detailed error information:

   ```sh
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- psql
   ```

   Check subscription statistics for error counts:

   ```sql
   SELECT subname,
          apply_error_count,
          sync_error_count,
          stats_reset,
          CASE
            WHEN apply_error_count > 0 THEN 'APPLY ERRORS DETECTED'
            WHEN sync_error_count > 0 THEN 'SYNC ERRORS DETECTED'
            ELSE 'HEALTHY'
          END as status
   FROM pg_stat_subscription_stats
   ORDER BY apply_error_count DESC, sync_error_count DESC;
   ```

2. Check the PostgreSQL logs for detailed error messages:

   ```bash
   kubectl logs services/paradedb-rw --namespace NAMESPACE | jq 'select(.record.error_severity == "ERROR" and .record.backend_type == "logical replication apply worker")'
   ```

   Look for error patterns like:
   * `duplicate key value violates unique constraint`
   * `insert or update on table violates foreign key constraint`
   * `permission denied for table`
   * `column does not exist`
   * `check constraint violation`

3. Check the subscription status and current LSN position:

   ```sql
   SELECT s.subname,
          s.subenabled,
          s.subskiplsn,
          s.received_lsn,
          s.latest_end_lsn,
          pg_size_pretty(pg_wal_lsn_diff(s.received_lsn, s.latest_end_lsn)) as pending_lag
   FROM pg_subscription s
   ORDER BY s.subname;
   ```

4. Check for tables that might be stuck in synchronization:

   ```sql
   SELECT sub.subname,
          sr.srrelid::regclass AS table_name,
          sr.srsubstate,
          CASE sr.srsubstate
            WHEN 'i' THEN 'initialize'
            WHEN 'd' THEN 'data is being copied'
            WHEN 'f' THEN 'finished table copy'
            WHEN 's' THEN 'synchronized'
            WHEN 'r' THEN 'ready (normal replication)'
            ELSE sr.srsubstate
          END as state_description
   FROM pg_subscription_rel AS sr
   JOIN pg_subscription AS sub ON sub.oid = sr.srsubid
   WHERE sr.srsubstate != 'r'
   ORDER BY sub.subname, table_name;
   ```

5. If you suspect schema mismatches, compare table structures between publisher and subscriber:

   ```sql
   -- On subscriber
   SELECT table_name, column_name, data_type, is_nullable
   FROM information_schema.columns
   WHERE table_name IN ('table1', 'table2') -- Replace with problematic tables
   ORDER BY table_name, ordinal_position;
   ```

## Mitigation

### **For Constraint Violations:**

1. **Identify the conflicting data:**
   ```sql
   -- Find duplicate key violations
   SELECT key_column, COUNT(*) as duplicate_count
   FROM problematic_table
   GROUP BY key_column
   HAVING COUNT(*) > 1;
   ```

2. **Skip the conflicting transaction:**
   First, identify the LSN from the error logs, then:
   ```sql
   ALTER SUBSCRIPTION subscription_name SKIP (lsn = 'conflicting_lsn');
   ```

3. **Manually resolve the conflict:**
   ```sql
   -- Option 1: Update conflicting row
   UPDATE problematic_table
   SET conflicting_column = new_value
   WHERE primary_key = conflicting_key;

   -- Option 2: Delete duplicate row
   DELETE FROM problematic_table
   WHERE primary_key = duplicate_key
     AND ctid NOT IN (SELECT min(ctid) FROM problematic_table GROUP BY primary_key);
   ```

### **For Permission Issues:**

1. **Grant necessary privileges:**
   ```sql
   GRANT SELECT, INSERT, UPDATE, DELETE ON problematic_table TO subscription_user;
   GRANT USAGE ON SCHEMA schema_name TO subscription_user;
   GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA schema_name TO subscription_user;
   ```

2. **Verify subscription user permissions:**
   ```sql
   SELECT usename, usecreatedb, usesuper, usecreaterole
   FROM pg_user
   WHERE usename = 'subscription_user';

   -- Check schema privileges
   SELECT nspname, rolname, privilege_type
   FROM information_schema.role_table_grants
   WHERE grantee = current_user;
   ```

### **For Schema Mismatches:**

1. **Compare and fix schema differences:**
   ```sql
   -- Add missing columns
   ALTER TABLE problematic_table ADD COLUMN missing_column data_type;

   -- Modify column types (may require casting)
   ALTER TABLE problematic_table ALTER COLUMN existing_column TYPE new_type;
   ```

2. **Refresh publication if schema changed:**
   ```sql
   ALTER PUBLICATION publication_name REFRESH PUBLICATION;
   ```

### **For Row Level Security Issues:**

1. **Temporarily disable RLS for replication:**
   ```sql
   ALTER TABLE problematic_table DISABLE ROW LEVEL SECURITY;
   -- Replication should proceed
   ALTER TABLE problematic_table ENABLE ROW LEVEL SECURITY;
   ```

2. **Create RLS policies that allow replication:**
   ```sql
   CREATE POLICY allow_replication ON problematic_table
   FOR ALL TO subscription_user
   USING (true);
   ```

### **Re-enable the subscription:**

```sql
ALTER SUBSCRIPTION subscription_name ENABLE;
```

### **Verify recovery:**

```sql
-- Check that errors are not increasing
SELECT subname, apply_error_count, sync_error_count,
       CASE
         WHEN apply_error_count > LAG(apply_error_count) OVER (ORDER BY stats_reset) THEN 'STILL INCREASING'
         ELSE 'STABLE'
       END as trend
FROM pg_stat_subscription_stats;
```

### **Preventive Measures:**

* **Regular schema audits**: Periodically compare publisher and subscriber schemas.
* **Test schema changes**: Always test DDL changes in a staging environment first.
* **Monitor error trends**: Set up alerts for increasing error counts.
* **Data validation**: Implement regular data consistency checks between publisher and subscriber.
* **Backup strategies**: Maintain recent backups to allow quick recovery from data corruption.

## Comparison with Other Similar Alerts

| Alert Type | Measures | Indicates | Primary Target for Resolution |
|------------|----------|------------|------------------------------|
| **Apply Errors** | `increase(apply_error_count[5m])` | Data/application errors during **apply phase** | Data conflicts, schema issues, permissions, constraints |
| **Sync Errors** | `increase(sync_error_count[5m])` | Errors during initial **table synchronization** | Network issues, large table sync failures, permissions |
| **Critical Errors** | `total_errors >= 5 in 15m` | **Persistent or severe** replication issues | Systemic problems, configuration issues, multiple failure points |

**Key Difference**: Apply errors specifically target **data application failures** after successful receipt, while sync errors occur during the initial table copy phase. Apply errors often require manual data resolution, while sync errors are typically infrastructure-related.

[cloudnativepg-dashboard]: https://grafana.com/grafana/dashboards/20417-cloudnativepg/