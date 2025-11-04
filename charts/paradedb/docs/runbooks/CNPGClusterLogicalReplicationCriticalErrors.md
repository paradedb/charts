# CNPGClusterLogicalReplicationCriticalErrors

## Meaning

The `CNPGClusterLogicalReplicationCriticalErrors` alert indicates that a CloudNativePG cluster with a logical replication subscription has experienced 5 or more errors (both apply and sync errors combined) over the last 15 minutes. This sustained error rate suggests **systemic replication problems** that require immediate attention.

A critical error state indicates that the logical replication system is experiencing **persistent failures** rather than isolated incidents. This could be due to:

* **Configuration issues**: Incorrect subscription or publication setup.
* **Systemic resource problems**: Chronic CPU, memory, or I/O bottlenecks.
* **Network instability**: Persistent connectivity problems between publisher and subscriber.
* **Data corruption**: Widespread data conflicts or integrity issues.
* **Schema drift**: Significant differences between publisher and subscriber schemas.
* **Cascading failures**: Multiple dependent tables or relationships causing compound errors.

## Impact

The logical replication system is in a degraded state with potentially complete cessation of data replication. Depending on the error types, this could result in:

* Complete halt of new data replication
* Inconsistent data state between publisher and subscriber
* Potential data corruption if errors are related to constraint violations
* Extended periods of data unavailability for applications relying on the subscriber

## Diagnosis

1. **Immediate assessment of error rates:**

   ```sh
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- psql
   ```

   ```sql
   SELECT subname,
          apply_error_count,
          sync_error_count,
          apply_error_count + sync_error_count AS total_errors,
          stats_reset,
          CASE
            WHEN apply_error_count + sync_error_count >= 10 THEN 'CRITICAL'
            WHEN apply_error_count + sync_error_count >= 5 THEN 'WARNING'
            ELSE 'HEALTHY'
          END as severity
   FROM pg_stat_subscription_stats
   ORDER BY total_errors DESC;
   ```

2. **Check error trends and patterns:**

   ```sql
   -- Monitor error progression (requires querying multiple times)
   SELECT now() as check_time,
          subname,
          apply_error_count,
          sync_error_count,
          apply_error_count + sync_error_count AS total_errors
   FROM pg_stat_subscription_stats
   ORDER BY subname;
   ```

3. **Comprehensive log analysis:**

   ```bash
   # Get recent errors from the last 30 minutes
   kubectl logs services/paradedb-rw --namespace NAMESPACE --since=30m | \
   jq 'select(.record.error_severity == "ERROR" and .record.backend_type | contains("replication"))'

   # Count error types
   kubectl logs services/paradedb-rw --namespace NAMESPACE --since=30m | \
   jq -r '.record.message | capture("(?i)<errtype> (?<errtype>constraint|permission|connection|timeout)")' | \
   sort | uniq -c
   ```

4. **System-wide health check:**

   ```sql
   -- Check subscription status
   SELECT subname, subenabled, subconninfo, subslotname
   FROM pg_subscription
   ORDER BY subname;

   -- Check worker processes
   SELECT s.subname, s.worker_type, s.pid,
          a.state, a.wait_event_type, a.wait_event,
          now() - a.query_start as query_duration
   FROM pg_stat_subscription s
   LEFT JOIN pg_stat_activity a ON a.pid = s.pid
   ORDER BY s.subname, s.worker_type;

   -- Check table sync status
   SELECT sub.subname, COUNT(*) as table_count,
          COUNT(CASE WHEN sr.srsubstate != 'r' THEN 1 END) as not_ready
   FROM pg_subscription_rel sr
   JOIN pg_subscription sub ON sub.oid = sr.srsubid
   GROUP BY sub.subname;
   ```

5. **Resource utilization assessment:**

   ```bash
   # Check system resources
   kubectl top pods --namespace NAMESPACE
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- df -h
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- free -h

   # Check PostgreSQL resource usage
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- psql -c "
     SELECT datname, numbackends, xact_commit, xact_rollback,
            blks_read, blks_hit, tup_returned, tup_fetched,
            tup_inserted, tup_updated, tup_deleted
     FROM pg_stat_database
     WHERE datname NOT IN ('template0', 'template1', 'postgres');
   "
   ```

## Mitigation

### **Phase 1: Stabilize the System**

1. **Pause replication to prevent further errors:**
   ```sql
   ALTER SUBSCRIPTION subscription_name DISABLE;
   ```

2. **Assess and resolve immediate resource issues:**
   ```bash
   # Free up disk space if needed
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- find /var/lib/postgresql/data -name "*.log" -mtime +7 -delete

   # Scale up resources if under pressure
   kubectl patch deployment paradedb --namespace NAMESPACE -p '{"spec":{"template":{"spec":{"containers":[{"name":"postgres","resources":{"requests":{"memory":"4Gi","cpu":"2000m"},"limits":{"memory":"8Gi","cpu":"4000m"}}}]}}}}'
   ```

3. **Identify and categorize error sources:**

   ```sql
   -- Check for specific error patterns in recent logs
   SELECT error_count, error_type, first_occurrence, last_occurrence
   FROM (
     SELECT COUNT(*) as error_count,
            CASE
              WHEN message LIKE '%constraint%' THEN 'CONSTRAINT'
              WHEN message LIKE '%permission%' THEN 'PERMISSION'
              WHEN message LIKE '%connection%' THEN 'CONNECTION'
              WHEN message LIKE '%timeout%' THEN 'TIMEOUT'
              WHEN message LIKE '%disk full%' THEN 'DISK_SPACE'
              ELSE 'OTHER'
            END as error_type,
            MIN(log_time) as first_occurrence,
            MAX(log_time) as last_occurrence
     FROM pg_stat_statements  -- This is conceptual - actual implementation depends on log parsing
     WHERE error_severity = 'ERROR'
     GROUP BY
       CASE
         WHEN message LIKE '%constraint%' THEN 'CONSTRAINT'
         WHEN message LIKE '%permission%' THEN 'PERMISSION'
         WHEN message LIKE '%connection%' THEN 'CONNECTION'
         WHEN message LIKE '%timeout%' THEN 'TIMEOUT'
         WHEN message LIKE '%disk full%' THEN 'DISK_SPACE'
         ELSE 'OTHER'
       END
   ) error_analysis
   ORDER BY error_count DESC;
   ```

### **Phase 2: Address Root Causes**

**For Constraint Violations:**
```sql
-- Find and resolve data conflicts systematically
WITH conflicting_rows AS (
  SELECT 'table_name' as table_name, 'id_column' as conflicting_column, COUNT(*) as conflict_count
  FROM problematic_table
  GROUP BY id_column
  HAVING COUNT(*) > 1
)
SELECT * FROM conflicting_rows;

-- Systematically resolve conflicts
-- This may require data cleanup, schema adjustments, or business logic changes
```

**For Permission Issues:**
```sql
-- Grant comprehensive permissions
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
    LOOP
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE %I.%I TO replication_user', r.schemaname, r.tablename);
        EXECUTE format('GRANT USAGE ON SCHEMA %I TO replication_user', r.schemaname);
    END LOOP;
END $$;
```

**For Connectivity Issues:**
```bash
# Test network stability
for i in {1..10}; do
  kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- nc -zv publisher_host 5432
  sleep 5
done

# Check network policies
kubectl get networkpolicy --namespace NAMESPACE
```

**For Resource Issues:**
```yaml
# Increase resources permanently
spec:
  template:
    spec:
      containers:
      - name: postgres
        resources:
          requests:
            memory: "8Gi"
            cpu: "4000m"
          limits:
            memory: "16Gi"
            cpu: "8000m"
        volumeMounts:
        - name: wal-storage
          mountPath: /var/lib/postgresql/wal
      volumes:
      - name: wal-storage
        persistentVolumeClaim:
          claimName: paradedb-wal
```

### **Phase 3: Recreate and Restore Replication**

1. **Consider fresh subscription setup:**
   ```sql
   -- Backup current subscription state
   CREATE TABLE subscription_backup AS
   SELECT * FROM pg_subscription;

   -- Drop and recreate subscription
   DROP SUBSCRIPTION subscription_name;

   CREATE SUBSCRIPTION subscription_name
   CONNECTION 'connection_string'
   PUBLICATION publication_name
   WITH (copy_data = true, create_slot = false);
   ```

2. **Use staged synchronization for large datasets:**
   ```sql
   -- Create subscription without data copy
   CREATE SUBSCRIPTION subscription_name
   CONNECTION 'connection_string'
   PUBLICATION publication_name
   WITH (copy_data = false);

   -- Manually sync tables using optimized methods
   -- This might involve:
   -- - pg_dump with custom format and parallel restore
   -- - External ETL tools for large datasets
   -- - Incremental synchronization approaches
   ```

3. **Verify recovery:**
   ```sql
   -- Monitor error counts
   SELECT subname, apply_error_count, sync_error_count, stats_reset
   FROM pg_stat_subscription_stats;

   -- Check replication progress
   SELECT subname,
          pg_size_pretty(pg_wal_lsn_diff(received_lsn, latest_end_lsn)) as lag,
          received_lsn, latest_end_lsn
   FROM pg_stat_subscription;
   ```

### **Phase 4: Preventive Monitoring**

1. **Set up comprehensive monitoring:**
   ```sql
   -- Create monitoring views
   CREATE VIEW replication_health AS
   SELECT s.subname,
          s.subenabled,
          s.apply_error_count + s.sync_error_count as total_errors,
          pg_wal_lsn_diff(s.received_lsn, s.latest_end_lsn) as lag_bytes,
          NOW() - s.latest_end_time as apply_lag_seconds,
          CASE
            WHEN s.apply_error_count + s.sync_error_count >= 5 THEN 'CRITICAL'
            WHEN pg_wal_lsn_diff(s.received_lsn, s.latest_end_lsn) > 10*1024^3 THEN 'WARNING'
            ELSE 'HEALTHY'
          END as health_status
   FROM pg_stat_subscription s;
   ```

2. **Implement regular health checks:**
   ```bash
   # Create monitoring cronjob or external health check
   kubectl create cronjob replication-health-check --schedule="*/5 * * * *" --image=postgres:15 --namespace NAMESPACE -- "psql -h paradedb-rw -U postgres -d paradedb -c 'SELECT * FROM replication_health;'"
   ```

## Comparison with Other Similar Alerts

| Alert Type | Measures | Indicates | Primary Target for Resolution |
|------------|----------|------------|------------------------------|
| **Critical Errors** | `total_errors >= 5 in 15m` | **Systemic or persistent** replication problems | System-wide resources, configuration, architecture |
| **Apply Errors** | `increase(apply_error_count[5m])` | Data/application errors during **apply phase** | Data conflicts, schema issues, permissions, constraints |
| **Sync Errors** | `increase(sync_error_count[5m])` | Errors during **initial table synchronization** phase | Network connectivity, large table copy issues, permissions |
| **High Error Rate** | `error_rate > 0.5/min` | **Sustained low-level** replication issues | Chronic performance problems, resource bottlenecks |

**Key Difference**: Critical errors represent **system-wide failures** requiring comprehensive diagnosis and potentially complete replication system reset. Other error types are more specific and can often be resolved with targeted fixes, while critical errors may indicate fundamental architectural or resource problems.

[cloudnativepg-dashboard]: https://grafana.com/grafana/dashboards/20417-cloudnativepg/