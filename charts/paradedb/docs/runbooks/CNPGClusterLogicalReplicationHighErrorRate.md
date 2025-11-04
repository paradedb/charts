# CNPGClusterLogicalReplicationHighErrorRate

## Meaning

The `CNPGClusterLogicalReplicationHighErrorRate` alert indicates that a CloudNativePG cluster with a logical replication subscription is experiencing a sustained error rate of more than 0.5 errors per minute (approximately 1 error every 2 minutes) over the last 10 minutes. This suggests **chronic replication problems** that may not trigger immediate critical alerts but indicate persistent system issues.

A high error rate differs from critical errors in that it represents a **sustained pattern of failures** rather than a sudden burst. This often indicates:

* **Chronic resource constraints**: Consistently insufficient CPU, memory, or I/O capacity.
* **Performance degradation**: Gradual system performance decline leading to time-outs or failures.
* **Configuration suboptimal**: Settings that work under light load but fail under sustained pressure.
* **Recurring data conflicts**: Ongoing issues with data consistency or constraint violations.
* **Network instability**: Intermittent connectivity problems that resolve and recur.
* **Workload patterns**: Specific workloads or times that consistently trigger errors.

## Impact

The logical replication system continues to function but with reduced reliability and data consistency. The impact includes:

* Gradual data divergence between publisher and subscriber
* Intermittent periods of stale data on subscriber
* Reduced confidence in replication system reliability
* Potential for escalation to critical error states if not addressed
* Application performance degradation during error recovery periods

## Diagnosis

1. **Analyze error rate trends:**

   ```sh
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- psql
   ```

   ```sql
   -- Monitor error progression over time
   SELECT now() as check_time,
          subname,
          apply_error_count,
          sync_error_count,
          apply_error_count + sync_error_count AS total_errors,
          ROUND(
            (apply_error_count + sync_error_count)::numeric /
            EXTRACT(EPOCH FROM (NOW() - stats_reset)) * 60, 2
          ) as errors_per_minute
   FROM pg_stat_subscription_stats
   WHERE stats_reset IS NOT NULL
   ORDER BY total_errors DESC;
   ```

2. **Identify error patterns and timing:**

   ```bash
   # Analyze error timing patterns
   kubectl logs services/paradedb-rw --namespace NAMESPACE --since=1h | \
   jq -r '.record.log_time + " " + .record.message' | \
   grep -i error | \
   awk '{print $1 " " substr($2,1,5)}' | \
   sort | uniq -c | \
   awk '$1 > 1 {print $0}'

   # Check for workload correlation
   kubectl logs services/paradedb-rw --namespace NAMESPACE --since=1h | \
   jq 'select(.record.error_severity == "ERROR") | {time: .record.log_time, message: .record.message}'
   ```

3. **Performance and resource utilization analysis:**

   ```sql
   -- Check system performance during error periods
   SELECT schemaname,
          tablename,
          seq_scan,
          seq_tup_read,
          idx_scan,
          idx_tup_fetch,
          n_tup_ins,
          n_tup_upd,
          n_tup_del,
          n_live_tup,
          n_dead_tup
   FROM pg_stat_user_tables
   ORDER BY n_tup_upd + n_tup_ins DESC
   LIMIT 20;

   -- Check wait events during replication
   SELECT s.subname,
          s.worker_type,
          a.wait_event_type,
          a.wait_event,
          COUNT(*) as occurrence_count
   FROM pg_stat_subscription s
   JOIN pg_stat_activity a ON a.pid = s.pid
   WHERE a.wait_event_type IS NOT NULL
   GROUP BY s.subname, s.worker_type, a.wait_event_type, a.wait_event
   ORDER BY occurrence_count DESC;
   ```

4. **Correlate errors with workload patterns:**

   ```sql
   -- Identify high-activity periods that might correlate with errors
   SELECT now() - interval '1 hour' as start_time,
          now() as current_time,
          SUM(xact_commit + xact_rollback) as total_transactions,
          SUM(tup_returned + tup_fetched + tup_inserted + tup_updated + tup_deleted) as total_tuple_activity
   FROM pg_stat_database
   WHERE datname = current_database();
   ```

5. **Network and connectivity assessment:**

   ```bash
   # Monitor network performance
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- \
   ping -c 10 publisher_host | tail -3

   # Check connection pool status
   kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- \
   psql -c "SELECT * FROM pg_stat_activity WHERE application_name LIKE '%replication%';"
   ```

## Mitigation

### **Phase 1: Pattern Analysis**

1. **Identify error patterns:**
   ```bash
   # Create error pattern analysis
   kubectl logs services/paradedb-rw --namespace NAMESPACE --since=6h | \
   jq -r 'select(.record.error_severity == "ERROR") | .record.message' | \
   sed 's/.*\([A-Z][A-Z_]*\).*/\1/' | \
   sort | uniq -c | sort -nr
   ```

2. **Correlate with system metrics:**
   ```sql
   -- Create a monitoring function to track correlation
   CREATE OR REPLACE FUNCTION analyze_replication_performance()
   RETURNS TABLE(
     timestamp timestamptz,
     error_count bigint,
     transaction_rate numeric,
     cpu_usage numeric,
     memory_usage numeric
   ) AS $$
   BEGIN
     RETURN QUERY
     SELECT
       NOW() as timestamp,
       (SELECT apply_error_count + sync_error_count FROM pg_stat_subscription_stats LIMIT 1),
       (SELECT SUM(xact_commit + xact_rollback) FROM pg_stat_database WHERE datname = current_database()),
       -- Add system metrics collection here
       0 as cpu_usage, -- Placeholder for system metrics
       0 as memory_usage; -- Placeholder for system metrics
   END;
   $$ LANGUAGE plpgsql;
   ```

### **Phase 2: Resource Optimization**

1. **Adjust worker configuration for sustained load:**
   ```sql
   -- Increase replication workers for sustained performance
   -- Helm: cluster.postgresql.parameters.max_logical_replication_workers
   -- Terraform: paradedb.postgresql.parameters.max_logical_replication_workers

   -- Recommended for high-error-rate scenarios:
   SET max_logical_replication_workers = 10;
   SET max_parallel_workers = 8;
   SET max_worker_processes = 20;
   ```

2. **Optimize connection management:**
   ```sql
   -- Adjust connection timeouts for better stability
   ALTER SYSTEM SET statement_timeout = '300s';
   ALTER SYSTEM SET lock_timeout = '60s';
   ALTER SYSTEM SET idle_in_transaction_session_timeout = '600s';

   -- Reload configuration
   SELECT pg_reload_conf();
   ```

3. **Implement connection pooling:**
   ```sql
   -- Configure PgBouncer or similar for connection management
   -- This helps maintain stable connections under sustained load
   ```

### **Phase 3: Workload and Configuration Tuning**

1. **Implement batch processing optimizations:**
   ```sql
   -- Adjust batch sizes if using custom replication
   ALTER SYSTEM SET wal_writer_delay = '200ms';
   ALTER SYSTEM SET commit_delay = '1000';
   ALTER SYSTEM SET commit_siblings = 5;
   ```

2. **Optimize publication for sustained load:**
   ```sql
   -- Review and optimize publication tables
   SELECT schemaname, tablename, n_tup_ins, n_tup_upd, n_tup_del
   FROM pg_stat_user_tables
   WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
   ORDER BY n_tup_ins + n_tup_upd + n_tup_del DESC;

   -- Consider removing high-change tables from publication if not critical
   ALTER PUBLICATION publication_name DROP TABLE problematic_table;
   ```

3. **Implement monitoring and alerting for early detection:**
   ```sql
   -- Create monitoring view for error rate trends
   CREATE VIEW error_rate_monitoring AS
   SELECT
     subname,
     apply_error_count,
     sync_error_count,
     (apply_error_count + sync_error_count) as total_errors,
     CASE
       WHEN stats_reset > NOW() - INTERVAL '1 hour' THEN
         ROUND((apply_error_count + sync_error_count)::numeric /
               EXTRACT(EPOCH FROM (NOW() - stats_reset)) * 60, 2)
       ELSE 0
     END as errors_per_minute,
     CASE
       WHEN (apply_error_count + sync_error_count)::numeric /
            EXTRACT(EPOCH FROM (NOW() - stats_reset)) * 60 > 0.5 THEN 'HIGH'
       WHEN (apply_error_count + sync_error_count)::numeric /
            EXTRACT(EPOCH FROM (NOW() - stats_reset)) * 60 > 0.1 THEN 'ELEVATED'
       ELSE 'NORMAL'
     END as error_rate_status
   FROM pg_stat_subscription_stats;
   ```

### **Phase 4: Advanced Mitigation Strategies**

1. **Implement subscription partitioning:**
   ```sql
   -- Split large publications into smaller, more manageable subscriptions
   CREATE PUBLICATION critical_tables_pub FOR TABLE table1, table2, table3;
   CREATE PUBLICATION reference_data_pub FOR TABLE ref_table1, ref_table2;
   CREATE PUBLICATION logging_tables_pub FOR TABLE log_table1, log_table2;

   -- Create corresponding subscriptions
   CREATE SUBSCRIPTION critical_sub CONNECTION '...' PUBLICATION critical_tables_pub;
   CREATE SUBSCRIPTION reference_sub CONNECTION '...' PUBLICATION reference_data_pub;
   CREATE SUBSCRIPTION logging_sub CONNECTION '...' PUBLICATION logging_tables_pub;
   ```

2. **Implement scheduled maintenance windows:**
   ```bash
   # Create Kubernetes cronjob for regular maintenance
   cat <<EOF | kubectl apply -f -
   apiVersion: batch/v1
   kind: CronJob
   metadata:
     name: replication-maintenance
     namespace: NAMESPACE
   spec:
     schedule: "0 2 * * *"  # Daily at 2 AM
     jobTemplate:
       spec:
         template:
           spec:
             containers:
             - name: maintenance
               image: postgres:15
               command:
               - /bin/bash
               - -c
               - |
                 psql -h paradedb-rw -U postgres -d paradedb -c "
                   VACUUM ANALYZE;
                   SELECT pg_stat_reset();
                   ALTER SUBSCRIPTION subscription_name REFRESH PUBLICATION;
                 "
             restartPolicy: OnFailure
   EOF
   ```

3. **Consider architecture changes:**
   * **Read replicas**: Offload read queries from subscriber to dedicated read replicas
   * **Logical decoding**: Use logical decoding for streaming analytics instead of full replication
   * **Change Data Capture (CDC)**: Implement CDC patterns for specific use cases
   * **Hybrid approach**: Combine physical and logical replication for different use cases

### **Phase 5: Monitoring and Prevention**

1. **Set up predictive monitoring:**
   ```sql
   -- Create predictive alerting function
   CREATE OR REPLACE FUNCTION predict_replication_issues()
   RETURNS TABLE(
     subscription text,
     risk_level text,
     predicted_issue text,
     recommended_action text
   ) AS $$
   BEGIN
     RETURN QUERY
     SELECT
       subname,
       CASE
         WHEN (apply_error_count + sync_error_count)::numeric /
              EXTRACT(EPOCH FROM (NOW() - stats_reset)) * 60 > 1.0 THEN 'HIGH'
         WHEN (apply_error_count + sync_error_count)::numeric /
              EXTRACT(EPOCH FROM (NOW() - stats_reset)) * 60 > 0.3 THEN 'MEDIUM'
         ELSE 'LOW'
       END as risk_level,
       CASE
         WHEN (apply_error_count + sync_error_count)::numeric /
              EXTRACT(EPOCH FROM (NOW() - stats_reset)) * 60 > 1.0 THEN 'IMMEDIATE CRITICAL ERROR EXPECTED'
         WHEN (apply_error_count + sync_error_count)::numeric /
              EXTRACT(EPOCH FROM (NOW() - stats_reset)) * 60 > 0.3 THEN 'PERFORMANCE DEGRADATION LIKELY'
         ELSE 'NORMAL OPERATION'
       END as predicted_issue,
       CASE
         WHEN (apply_error_count + sync_error_count)::numeric /
              EXTRACT(EPOCH FROM (NOW() - stats_reset)) * 60 > 1.0 THEN 'SCALE UP RESOURCES, CHECK CONFIGURATION'
         WHEN (apply_error_count + sync_error_count)::numeric /
              EXTRACT(EPOCH FROM (NOW() - stats_reset)) * 60 > 0.3 THEN 'MONITOR CLOSELY, OPTIMIZE WORKLOAD'
         ELSE 'CONTINUE MONITORING'
       END as recommended_action
     FROM pg_stat_subscription_stats;
   END;
   $$ LANGUAGE plpgsql;
   ```

## Comparison with Other Similar Alerts

| Alert Type | Measures | Indicates | Primary Target for Resolution |
|------------|----------|------------|------------------------------|
| **High Error Rate** | `error_rate > 0.5/min` over 10min | **Sustained low-level** replication issues | Chronic performance problems, resource bottlenecks, configuration optimization |
| **Critical Errors** | `total_errors >= 5 in 15m` | **Systemic or severe** replication problems | System-wide resources, configuration, architecture |
| **Apply Errors** | `increase(apply_error_count[5m])` | Data/application errors during **apply phase** | Data conflicts, schema issues, permissions, constraints |
| **Sync Errors** | `increase(sync_error_count[5m])` | Errors during **initial table synchronization** phase | Network connectivity, large table copy issues, permissions |

**Key Difference**: High error rate alerts focus on **sustained performance degradation patterns** rather than acute failures. They provide early warning of chronic issues that may not trigger immediate critical alerts but indicate underlying system stress or suboptimal configuration. This enables proactive optimization before problems escalate.

[cloudnativepg-dashboard]: https://grafana.com/grafana/dashboards/20417-cloudnativepg/