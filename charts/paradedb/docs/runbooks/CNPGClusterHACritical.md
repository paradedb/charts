CNPGClusterHACritical
=====================

Meaning
-------

The `CNPGClusterHACritical` alert is triggered when the CloudNativePG cluster has no ready standby replicas.

This can happen during either a normal failover or automated minor version upgrades in a cluster with 2 or less
instances. The replaced instance may need some time to catch up with the cluster primary instance.

This alert will always be triggered if your cluster is configured to run with only 1 instance. In this case you
may want to silence it.

Impact
------

Having no available replicas puts the cluster at severe risk if the primary instance also fails. The primary instance
is still online and able to serve queries, although connections to the `-ro` endpoint will fail. Failure of the primary
instance will result in a complete outage. Take effort to identify and protect the primary instance.

Diagnosis
---------

Use the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/).

You can identify the current primary instance or use the following command:

```bash
kubectl get cluster paradedb -o 'jsonpath={"Current Primary: "}{.status.currentPrimary}{"; Target Primary: "}{.status.targetPrimary}{"\n"}' --namespace NAMESPACE
```

Avoid making changes or operations that could negatively impact the primary instance as it is the only instance serving
queries.

Get the status of the CloudNativePG cluster instances:

```bash
kubectl get pods -A -l "cnpg.io/podRole=instance" -o wide
```

If the pods are Pending, describe the pods to identify the reason:

```bash
kubectl describe --namespace NAMESPACE pod/POD_NAME
```

Check the Cluster Phase and Phase Reason:

```bash
kubectl get cluster paradedb -o 'jsonpath={.status.phase}{"\n"}{.status.phaseReason}{"\n"}' --namespace NAMESPACE
```

Check the logs of the affected CloudNativePG instances:

```bash
kubectl logs --namespace <namespace> pod/<instance-pod-name>
```

Check the CloudNativePG operator logs:

```bash
kubectl logs --namespace cnpg-system -l "app.kubernetes.io/name=cloudnative-pg"
```

Mitigation
----------

Refer to the [CloudNativePG Failure Modes](https://cloudnative-pg.io/documentation/current/failure_modes/)
and [CloudNativePG Troubleshooting](https://cloudnative-pg.io/documentation/current/troubleshooting/) documentation for
more information on how to troubleshoot and mitigate this issue.

If the issue is due to insufficient storage, you should increase the cluster storage size. See this documentation for
more information on how to [Resize the CloudNativePG Cluster Storage](https://cloudnative-pg.io/documentation/current/troubleshooting/#storage-is-full).

If using the ParadeDB BYOC refer to `docs/handbook/NotEnoughDiskSpace.md` provided with the Terraform module.

If unable to determine the issue, you can attempt to recreate the affected pods. Make sure you do this only one pod at a
time to avoid increasing the load on the primary instance unnecessarily.

Very carefully verify that:
1. You are connected to the correct customer.
2. You are deleting the correct pod.
3. You are not deleting the active primary instance.

```bash
kubectl delete --namespace NAMESPACE pod/POD_NAME pvc/POD_NAME pvc/POD_NAME-wal
```
