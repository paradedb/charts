# CNPGClusterHA

## Description

The `CNPGClusterHAWarning` and `CNPGClusterHACritical` alerts are triggered when the CloudNativePG cluster has fewer than two ready standby replicas.

- **Warning level**: the cluster has one ready standby replica
- **Critical level**: the cluster has no ready standby replicas

Either may fire briefly during a regular failover or a planned automated version upgrade, while only the primary is active and the failover completes.

Both alerts remain active at all times on a single-instance cluster, and the warning does on a two-instance cluster. If running with that many instances is intentional, consider silencing the alert.

## Impact

With a single standby replica, the `-ro` endpoint is at risk of downtime if that replica fails. The cluster continues to function, but both the `-ro` and `-r` endpoints operate with reduced capacity.

With no standby replicas at all, the cluster will incur downtime if the primary fails, and connections through the `-ro` endpoint fail immediately. The primary itself remains online and able to serve queries.

## Diagnosis

Identify the current primary instance using the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/) or by running:

```bash
kubectl get -n <namespace> cluster/paradedb -o 'jsonpath={"Current Primary: "}{.status.currentPrimary}{"; Target Primary: "}{.status.targetPrimary}{"\n"}'
```

Since the primary may be the only instance serving queries, avoid making any changes that could disrupt it.

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

If the root cause remains unclear, recreating the affected pods can sometimes resolve the issue. Recreating a pod involves deleting the pod, its storage PVC, and its WAL storage PVC. This triggers a full rebuild of the instance from a base backup and can take several hours, depending on the size of the database.

> [!IMPORTANT]
> Recreate pods one at a time, to avoid increasing the load on the primary instance. Before deleting, verify that:
>
> - You are connected to the correct cluster.
> - You are deleting the correct pod.
> - You are not deleting the active primary instance.

```bash
kubectl delete -n <namespace> pod/<pod-name> pvc/<pod-name> pvc/<pod-name>-wal
```
