# CNPGClusterHACritical

## Description

The `CNPGClusterHACritical` alert is triggered when the CloudNativePG cluster has no ready standby replicas.

This alert may occur during a regular failover or a planned automated version upgrade on two-instance clusters, as there is a brief period when only the primary remains active while a failover completes.

On single-instance clusters, this alert will remain active at all times. If running with a single instance is intentional, consider silencing the alert.

## Impact

Without standby replicas, the cluster will incur downtime if the primary fails. While the primary instance remains online and able to serve queries, connections through the `-ro` endpoint will fail.

## Diagnosis

Identify the current primary instance using the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/) or by running:

```bash
kubectl get -n <namespace> cluster/paradedb -o 'jsonpath={"Current Primary: "}{.status.currentPrimary}{"; Target Primary: "}{.status.targetPrimary}{"\n"}'
```

Since the primary is the only instance serving queries, avoid making any changes that could disrupt it.

To inspect cluster health and instance status:

- Get the status of the CloudNativePG cluster instances:

```bash
kubectl get -n <namespace> pods -l "cnpg.io/podRole=instance" -o wide
```

- If any pods are Pending, describe them to identify the cause:

```bash
kubectl describe -n <namespace> pod/<pod-name>
```

- Inspect the cluster phase and reason:

```bash
kubectl get -n <namespace> cluster/paradedb -o 'jsonpath={.status.phase}{"\n"}{.status.phaseReason}{"\n"}'
```

- Inspect the logs of the affected CloudNativePG instances:

```bash
kubectl logs -n <namespace> pod/<instance-pod-name>
```

- Inspect the CloudNativePG operator logs:

```bash
kubectl logs -n cnpg-system -l "app.kubernetes.io/name=cloudnative-pg"
```

## Mitigation

### Instance Failure

Start with the [CloudNativePG Failure Modes](https://cloudnative-pg.io/documentation/current/failure_modes/) and [CloudNativePG Troubleshooting](https://cloudnative-pg.io/documentation/current/troubleshooting/) documentation, which cover the conditions under which CloudNativePG cannot heal an instance on its own.

### Insufficient Storage

If the above diagnosis commands indicate that an instance's storage or WAL disk is full, increase the cluster storage size. For more details, see the [CloudNativePG documentation on resizing storage](https://cloudnative-pg.io/documentation/current/troubleshooting/#storage-is-full).

### Unknown

If the root cause remains unclear, recreating the affected pods can sometimes resolve the issue. Recreating a pod involves deleting the pod, its storage PVC, and its WAL storage PVC. This will trigger a full rebuild of the node from a base backup and can take several hours, depending on the size of the database. Note that pods should **always** be recreated one at a time to avoid increasing the load on the primary instance.

Before doing so, carefully verify that:

- You are connected to the correct cluster.
- You are deleting the correct pod.
- You are not deleting the active primary instance.

```bash
kubectl delete -n <namespace> pod/<pod-name> pvc/<pod-name> pvc/<pod-name>-wal
```
