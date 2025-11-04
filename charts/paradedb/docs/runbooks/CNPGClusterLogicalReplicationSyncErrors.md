# CNPGClusterLogicalReplicationSyncErrors

## Meaning

The `CNPGClusterLogicalReplicationSyncErrors` alert indicates that a CloudNativePG cluster with a logical replication subscription has experienced one or more errors during the initial table synchronization phase. This is detected by an increase in the `sync_error_count` from `pg_stat_subscription_stats` over the last 5 minutes.

Sync errors occur during the **initial data copy** when setting up a subscription or when re-synchronizing tables. Unlike apply errors (which occur during ongoing replication), sync errors prevent the subscription from becoming fully operational. Common causes include:

* **Network connectivity issues**: Connection drops or timeouts during large data transfers.
* **Insufficient disk space**: Large tables may exceed available storage during copy operations.
* **Memory pressure**: Large table copies may exceed available memory on the subscriber.
* **Table locks**: Long-running transactions holding locks on publisher tables preventing data copy.
* **Permission failures**: The subscription user lacks necessary privileges for the initial data copy.
* **Timeout issues**: Large table copy operations exceeding configured timeouts.
* **Publication changes**: Tables being added or removed from publication during sync.

## Impact

The logical replication subscription cannot complete its initial setup or re-synchronization. Until sync errors are resolved, the subscription will not enter normal replication mode, and no data (initial or incremental) will be replicated from the publisher to the subscriber.

## Diagnosis

1. Connect via psql to check sync error status:

   ```sh
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- psql
   ```

   Check subscription statistics:

   ```sql
   SELECT subname,
          apply_error_count,
          sync_error_count,
          stats_reset,
          CASE
            WHEN sync_error_count > 0 THEN 'SYNC ERRORS DETECTED'
            WHEN apply_error_count > 0 THEN 'APPLY ERRORS DETECTED'
            ELSE 'HEALTHY'
          END as status
   FROM pg_stat_subscription_stats
   ORDER BY sync_error_count DESC, apply_error_count DESC;
   ```

2. Check which tables are currently synchronizing:

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
          END as state_description,
          pg_size_pretty(pg_total_relation_size(sr.srrelid)) as table_size
   FROM pg_subscription_rel AS sr
   JOIN pg_subscription AS sub ON sub.oid = sr.srsubid
   WHERE sr.srsubstate != 'r'
   ORDER BY sub.subname, pg_total_relation_size(sr.srrelid) DESC;
   ```

3. Check the PostgreSQL logs for sync-related error messages:

   ```bash
   kubectl logs services/paradedb-rw --namespace NAMESPACE | jq 'select(.record.error_severity == "ERROR" and (.record.message | contains("table copy") or .record.message | contains("synchronization") or .record.backend_type == "logical replication table sync worker"))'
   ```

   Look for error patterns like:
   * `could not connect to the publisher`
   * `out of memory`
   * `disk full`
   * `timeout expired`
   * `permission denied`

4. Check subscription status and configuration:

   ```sql
   SELECT subname,
          subenabled,
          subconninfo,
          subslotname,
          subsynccommit,
          subpublications
   FROM pg_subscription
   ORDER BY subname;
   ```

5. Check for network connectivity issues:

   ```sql
   -- Test connection to publisher (if possible)
   SELECT dblink_connect('publisher_conn', 'host=publisher_host port=5432 dbname=publication_db user=replication_user');
   ```

6. Monitor resource usage during sync operations:

   ```bash
   # Check disk space
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- df -h

   # Check memory usage
   kubectl top pods --namespace NAMESPACE

   # Check network connectivity
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- ping -c 3 publisher_host
   ```

## Mitigation

### **For Network Issues:**

1. **Check network connectivity:**
   ```bash
   # Test connectivity to publisher
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- nc -zv publisher_host 5432
   ```

2. **Verify connection string:**
   ```sql
   -- Update connection info if needed
   ALTER SUBSCRIPTION subscription_name CONNECTION 'host=publisher_host port=5432 dbname=publication_db user=replication_user password=secure_password';
   ```

3. **Check firewall rules and network policies** between publisher and subscriber clusters.

### **For Resource Issues:**

1. **Free up disk space:**
   ```bash
   # Clean up old logs and temporary files
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- find /tmp -name "*.tmp" -delete
   ```

2. **Scale up resources if needed:**
   ```yaml
   # Increase PVC size or use larger instance types
   # Consider adding temporary storage for sync operations
   ```

3. **Monitor resource limits:**
   ```bash
   # Check resource quotas and limits
   kubectl describe namespace NAMESPACE
   ```

### **For Large Table Synchronization:**

1. **Break up large publications:**
   ```sql
   -- Create separate publications for different table groups
   CREATE PUBLICATION small_tables_pub FOR TABLE table1, table2, table3;
   CREATE PUBLICATION large_tables_pub FOR TABLE large_table1, large_table2;

   -- Create separate subscriptions
   CREATE SUBSCRIPTION small_tables_sub CONNECTION '...' PUBLICATION small_tables_pub;
   CREATE SUBSCRIPTION large_tables_sub CONNECTION '...' PUBLICATION large_tables_pub WITH (copy_data = false);

   -- Manually copy large tables using pg_dump/pg_restore or other methods
   ```

2. **Use partial synchronization:**
   ```sql
   -- Create subscription without copying data initially
   CREATE SUBSCRIPTION subscription_name CONNECTION '...' PUBLICATION publication_name WITH (copy_data = false);

   -- Manually copy data using more efficient methods
   -- This allows you to use parallel dumps, compression, etc.
   ```

3. **Increase timeout settings:**
   ```sql
   -- Adjust PostgreSQL timeouts (may require restart)
   SET statement_timeout = '600s';
   SET lock_timeout = '300s';
   ```

### **For Permission Issues:**

1. **Verify subscription user has necessary permissions on publisher:**
   ```sql
   -- On publisher
   GRANT USAGE ON SCHEMA schema_name TO replication_user;
   GRANT SELECT ON ALL TABLES IN SCHEMA schema_name TO replication_user;
   GRANT SELECT ON ALL SEQUENCES IN SCHEMA schema_name TO replication_user;
   ```

2. **Check RLS policies on publisher tables:**
   ```sql
   -- On publisher
   ALTER TABLE problematic_table DISABLE ROW LEVEL SECURITY;
   -- Or create appropriate policies
   CREATE POLICY allow_replication ON problematic_table FOR ALL TO replication_user USING (true);
   ```

### **Restart Synchronization:**

1. **Reset and restart the subscription:**
   ```sql
   -- Disable subscription
   ALTER SUBSCRIPTION subscription_name DISABLE;

   -- Reset sync state (this will restart table copy)
   ALTER SUBSCRIPTION subscription_name REFRESH PUBLICATION;

   -- Re-enable subscription
   ALTER SUBSCRIPTION subscription_name ENABLE;
   ```

2. **For persistent issues, recreate the subscription:**
   ```sql
   -- Drop and recreate subscription
   DROP SUBSCRIPTION subscription_name;

   CREATE SUBSCRIPTION subscription_name
   CONNECTION 'connection_string'
   PUBLICATION publication_name
   WITH (copy_data = true, create_slot = false);
   ```

### **Preventive Measures:**

* **Resource planning**: Ensure sufficient disk space and memory for the largest tables.
* **Network optimization**: Use dedicated networks or bandwidth allocation for replication.
* **Staged synchronization**: Synchronize large tables during maintenance windows or off-peak hours.
* **Monitoring**: Set up alerts for resource usage during sync operations.
* **Testing**: Always test new subscriptions in staging before production deployment.

## Comparison with Other Similar Alerts

| Alert Type | Measures | Indicates | Primary Target for Resolution |
|------------|----------|------------|------------------------------|
| **Sync Errors** | `increase(sync_error_count[5m])` | Errors during **initial table synchronization** phase | Network connectivity, resource limits, large table copy issues |
| **Apply Errors** | `increase(apply_error_count[5m])` | Data/application errors during **ongoing replication** | Data conflicts, schema issues, permissions, constraints |
| **Critical Errors** | `total_errors >= 5 in 15m` | **Persistent or severe** replication issues | Systemic problems, configuration issues, multiple failure points |

**Key Difference**: Sync errors occur during the **one-time setup** of table replication and typically relate to infrastructure, connectivity, or resource issues. Apply errors occur during **ongoing operations** and usually relate to data conflicts or schema problems. Sync errors prevent the subscription from becoming operational, while apply errors interrupt an otherwise working subscription.

[cloudnativepg-dashboard]: https://grafana.com/grafana/dashboards/20417-cloudnativepg/