CNPGClusterHighReplicationLag
=============================

Meaning
-------

This alert is triggered when the replication lag of the CloudNativePG cluster exceed `1s`.

Impact
------

High replication lag can cause the cluster replicas to become out of sync. Queries to the `-r` and `-ro` endpoints may
return stale data. In the event of a failover, there may be data loss for the time period of the lag.

Diagnosis
---------

Use the [CloudNativePG Grafana Dashboard][grafana-dashboard].You can also use the following command to check the replication status of the CloudNativePG cluster instances:

```bash
kubectl exec --namespace <namespace> --stdin --tty services/<cluster_name>-rw -- psql -c "SELECT * FROM pg_stat_replication;"
```

High replication lag can be caused by a number of factors, including:
1. Network issues and network congestion of the node network interface
    * Check the network interface statistics using the Grafana Dashboard
      in the `Kubernetes Cluster` section.
2. High load on the primary or standby replicas
    * Check the CPU and Memory usage of the CloudNativePG cluster instances using the [Grafana Dashboard][grafana-dashboard]].
3. Disk IO bottlenecks on the replicas
    * Check the disk IO statistics using the [Grafana Dashboard][grafana-dashboard]].
4. Long-running queries
    * Check the `Stat Activity` section of the [CloudNativePG Grafana Dashboard][grafana-dashboard]].
5. Suboptimal PostgreSQL configuration, in particular a small number of `max_wal_senders`. It should be set to a number
  greater than or equal to the number of instances in your cluster. It defaults to `10` so it is usually sufficient for
  a clusters with less than 10 instances.
    * You can check active PostgreSQL parameter configuration using the
      [CloudNativePG Grafana Dashboard][grafana-dashboard]] in the `PostgreSQL Parameters` section.

Mitigation
----------

* Kill any long-running transactions that could be creating more changes than standby replicas are able to process.

  ```bash
  kubectl exec -it services/paradedb-rw --namespace NAMESPACE -- psql
  ```

* Increase the Memory and CPU resources of ParadeDB instances if they are under heavy load. You can do this by
  increasing the resource requests by setting `cluster.resources.requests` and `cluster.resources.limits` in your Helm
  values. It is highly recommended that you set both `requests` and `limits` to the same value to achieve QoS `Guaranteed`.
  This will require a restart of the CloudNativePG cluster instances and a primary switchover, which will cause a brief
  service disruption.

  If using the ParadeDB BYOC Terraform module, you can achieve the same thing by setting the `paradedb.cpu` and
  `paradedb.mem` parameters in the BYOC values.

* Enabling `wal_compression` by setting the `cluster.postgresql.parameters.wal_compression` parameter to `on`.
  might reduce the size of the WAL files and help reduce replication lag in a congested network.
  Changing `wal_compression` doesn't require a restart of the CloudNativePG cluster instances and normally can be done live.

  If you are using the ParadeDB BYOC Terraform module, you can set `paradedb.postgresql.parameters.wal_compression`.

* Increasing the number of IOPS or throughput of the storage used by the CloudNativePG cluster instances can help
  reduce replication lag if disk IO bottlenecked. Doing that requires creating a new storage class with higher IOPS or
  throughput and rebuilding cluster instances one by one using the new storage class. This is a slow process that will
  also affect the cluster's availability.

  If you decide to go this route:
  1. Start by creating a new storage class. Storage classes are immutable, so you cannot change the storage class of
    existing Persistent Volume Claims (PVCs).

    If using the ParadeDB BYOC Terraform module, add the new storage to the cluster's BYOC values - `k8s.storageClasses`.
  2. Make sure to only replace one instance at a time to avoid service disruption.
  3. Double check are deleting the correct pod.
  4. Don't start with the active primary instance. Delete one of the standby replicas first.

  ```bash
  kubectl delete --namespace NAMESPACE pod/POD_NAME pvc/POD_NAME pvc/POD_NAME-wal
  ```

* In the event that the cluster has 9+ instances make sure that the `max_wal_senders` parameter is set to a value
  greater than or equal to the total number of instances in your cluster.

[grafana-dashboard]: https://grafana.com/grafana/dashboards/20417-cloudnativepg/
