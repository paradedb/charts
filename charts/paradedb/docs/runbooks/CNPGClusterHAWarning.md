# CNPGClusterHAWarning

## Description

The `CNPGClusterHAWarning` alert is triggered when the CloudNativePG cluster has fewer than 2 ready standby replicas.

This alert will always be triggered if your cluster is configured to run with fewer than `3` instances. If this is intentional, you may want to silence it.

This can happen during a normal failover or automated minor version upgrades. The replaced instance may need some time to catch up with the cluster's primary instance. The alert will be triggered if the operation takes more than 5 minutes.

If the alert persists for longer than a few minutes, it may indicate a problem with the cluster. In that case, refer to the diagnosis and mitigation sections below.

## Impact

Having fewer than two available replicas puts the cluster at risk of downtime if another instance fails. The cluster is still able to operate normally, although the `-ro` and `-r` endpoints operate at reduced capacity.

At `0` available ready replicas, a `CNPGClusterHACritical` alert will be triggered.

## Diagnosis

You can identify the current primary instance with the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/) or via the following command:

```bash
kubectl get cluster paradedb -o 'jsonpath={"Current Primary: "}{.status.currentPrimary}{"; Target Primary: "}{.status.targetPrimary}{"\n"}' --namespace <namespace>
```

You can identify the current primary instance using the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/) or by running:

```bash
kubectl get cluster paradedb -o 'jsonpath={"Current Primary: "}{.status.currentPrimary}{"; Target Primary: "}{.status.targetPrimary}{"\n"}' --namespace <namespace>
```

Since the primary is the only instance serving queries, avoid making any changes that could disrupt it. To inspect cluster health and instance status:

- List cluster pods:

```bash
kubectl get pods -A -l "cnpg.io/podRole=instance" -o wide
```

- If any pods are Pending, describe them to identify the cause:

```bash
kubectl describe --namespace <namespace> pod/<pod-name>
```

- Check cluster phase and reason:

```bash
kubectl get cluster paradedb -o 'jsonpath={.status.phase}{"\n"}{.status.phaseReason}{"\n"}' --namespace <namespace>
```

- Review logs for affected instances:

```bash
kubectl logs --namespace <namespace> pod/<instance-pod-name>
```

- Review operator logs:

```bash
kubectl logs --namespace cnpg-system -l "app.kubernetes.io/name=cloudnative-pg"
```

## Mitigation

First, consult the [CloudNativePG Failure Modes](https://cloudnative-pg.io/documentation/current/failure_modes/) and [CloudNativePG Troubleshooting](https://cloudnative-pg.io/documentation/current/troubleshooting/) documentation for more information on the conditions when CloudNativePG is unable to heal instances and standard troubleshooting steps.

### Insufficient Storage

> [!NOTE]
> If you are using ParadeDB BYOC, refer to `docs/handbook/NotEnoughDiskSpace.md` included with the Terraform module.

If the above diagnosis commands indicate that one of the instance's storage disk or WAL storage disk are full, increase the cluster storage size. Refer to the CloudNativePG documentation for more information on how to [Resize the CloudNativePG Cluster Storage](https://cloudnative-pg.io/documentation/current/troubleshooting/#storage-is-full).

### Unknown

If the cause of the issue cannot be determined with certainty, it may be possible to resolve the situation by recreating the affected pods. Recreating a pod involves deleting the pod, its storage PVC, and its WAL storage PVC. Note that pods should be **always** be recreated one-at-a-time to avoid increasing the load on the primary instance.

Before doing so, carefully verify that:

- You are connected to the correct cluster.
- You are deleting the correct pod.
- You are not deleting the active primary instance.

```bash
kubectl delete --namespace <namespace> pod/<pod-name> pvc/<pod-name> pvc/<pod-name>-wal
```
