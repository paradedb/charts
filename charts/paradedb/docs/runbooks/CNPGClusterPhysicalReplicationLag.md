# CNPGClusterPhysicalReplicationLag

## Description

The `CNPGClusterPhysicalReplicationLagWarning` and `CNPGClusterPhysicalReplicationLagCritical` alerts are triggered when physical replication lag in the CloudNativePG cluster exceeds acceptable thresholds. Physical replication lag measures how far behind the standby replicas are from the primary instance.

- **Warning level**: replication lag exceeds 1 second
- **Critical level**: replication lag exceeds 15 seconds

## Impact

Physical replication lag can cause the cluster replicas to become out of sync. Queries to the `-r` and `-ro` endpoints may return stale data. In the event of a failover, the data that has not yet been replicated from the primary to the replicas may be lost.

At the warning level, the staleness is usually tolerable for read-heavy workloads. At the critical level, a failover carries a significant risk of data loss.

## Diagnosis

Check replication status in the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/) or by running:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/paradedb-rw -- psql -c "SELECT * FROM pg_stat_replication;"
```

High physical replication lag can be caused by a number of factors:

- Network congestion on the node interface, or insufficient bandwidth between the primary and its replicas. Inspect the network interface statistics using the `Kubernetes Cluster` section of the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/).

- High CPU or memory load on the primary or the replicas, or disk I/O bottlenecks on the replicas. Inspect the CPU, memory and disk I/O statistics using the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/), or run:

```bash
kubectl top pods --namespace <namespace> -l "cnpg.io/podRole=instance"
```

- Long-running transactions generating excessive changes. Inspect the `Stat Activity` section of the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/), or run:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/paradedb-rw -- psql -c "
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '5 minutes'
ORDER BY duration DESC;
"
```

- Suboptimal PostgreSQL configuration, for example too few `max_wal_senders`. Inspect the `PostgreSQL Parameters` section of the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/), or run:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/paradedb-rw -- psql -c "SHOW max_wal_senders; SHOW wal_compression;"
```

## Mitigation

- Terminate long-running transactions that generate excessive changes:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/paradedb-rw -- psql -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'active'
  AND now() - query_start > interval '30 minutes'
  AND query NOT LIKE '%autovacuum%';
"
```

- Increase the Memory and CPU resources of the instances under heavy load. This can be done by setting `cluster.resources.requests` and `cluster.resources.limits` in your Helm values. Set both `requests` and `limits` to the same value to achieve QoS Guaranteed. This will require a restart of the CloudNativePG cluster instances and a primary switchover, which will cause a brief service disruption.

- Enable `wal_compression` by setting the `cluster.postgresql.parameters.wal_compression` parameter to `on`. Doing so will reduce the size of the WAL files and can help reduce replication lag in a congested network. Changing `wal_compression` does not require a restart of the CloudNativePG cluster.

- In the event that the cluster has 9+ instances, ensure that the `cluster.postgresql.parameters.max_wal_senders` parameter is set to a value greater than or equal to the total number of instances in your cluster. The default of 10 is usually sufficient.

- Increase IOPS or throughput of the storage used by the cluster to alleviate disk I/O bottlenecks. This requires creating a new storage class with higher IOPS/throughput and rebuilding cluster instances and their PVCs one by one using the new storage class. This is a slow process that will also affect the cluster's availability.

If you decide to go this route:

1. Start by creating a new storage class. Storage classes are immutable, so you cannot change the storage class of existing Persistent Volume Claims (PVCs).

2. Make sure to only replace one instance at a time to avoid service disruption.

3. Double check you are deleting the correct pod.

4. Don't start with the active primary instance. Delete one of the standby replicas first.

```bash
kubectl delete --namespace <namespace> pod/<pod-name> pvc/<pod-name> pvc/<pod-name>-wal
```
