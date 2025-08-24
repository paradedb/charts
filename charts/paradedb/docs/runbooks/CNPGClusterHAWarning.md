CNPGClusterHAWarning
====================

Meaning
-------

The `CNPGClusterHAWarning` alert is triggered when the CloudNativePG cluster ready standby replicas are less than `2`.

This alert will always be triggered if your cluster is configured to run with less than `3` instances. In this case you may want to silence it.

This can happen during a normal failover or automated minor version upgrades. The replaced instance may need some time to catch up with the cluster's primary instance, which will trigger the alert if the operation takes more than 5 minutes.

If the alert persists for longer than a couple of minutes, it may indicate a problem with the cluster. In that case, refer to the diagnosis and mitigation sections below.

Impact
------

Having less than two available replicas puts your cluster at risk if another instance fails. The cluster is still able to operate normally, although the `-ro` and `-r` endpoints operate at reduced capacity.

At `0` available ready replicas, a `CNPGClusterHACritical` alert will be triggered.

Diagnosis
---------

Use the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/).

You can identify the current primary instance or use the following command:

```bash
kubectl get cluster paradedb -o 'jsonpath={"Current Primary: "}{.status.currentPrimary}{"; Target Primary: "}{.status.targetPrimary}{"\n"}' --namespace NAMESPACE
```

Avoid making changes or operations that could negatively impact the primary instance as it is the only instance serving queries.

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
and [CloudNativePG Troubleshooting](https://cloudnative-pg.io/documentation/current/troubleshooting/) documentation for more information on how to troubleshoot and mitigate this issue.

If the issue is due to insufficient storage, you should increase the cluster storage size. See this documentation for more information on how to [Resize the CloudNativePG Cluster Storage](https://cloudnative-pg.io/documentation/current/troubleshooting/#storage-is-full).

If using the ParadeDB BYOC refer to `docs/handbook/NotEnoughDiskSpace.md` provided with the Terraform module.

If unable to determine the issue, you can attempt to recreate the affected pods. Make sure you do this only one pod at a time to avoid increasing the load on the primary instance unnecessarily.

Very carefully verify that:

1. You are connected to the correct cluster.
2. You are deleting the correct pod.
3. You are not deleting the active primary instance.

```bash
kubectl delete --namespace NAMESPACE pod/POD_NAME pvc/POD_NAME pvc/POD_NAME-wal
```
