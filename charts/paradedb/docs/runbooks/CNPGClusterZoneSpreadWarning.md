# CNPGClusterZoneSpreadWarning

## Description

The `CNPGClusterZoneSpreadWarning` alert is triggered when pods are not evenly distributed across availability zones, specifically when the number of pods exceeds the number of zones and the cluster runs in fewer than three zones.

This can be caused by insufficient nodes in the cluster or by misconfigured scheduling rules, such as pod affinity/anti-affinity rules or tolerations.

## Impact

The uneven distribution of pods across availability zones increases the risk of a single point of failure if a zone becomes unavailable.

## Diagnosis

To investigate pod distribution across zones:

- Get the status of the CloudNativePG cluster instances:

```bash
kubectl get -n <namespace> pods -l "cnpg.io/podRole=instance" -o wide
```

- Get the nodes and their respective zones:

```bash
kubectl get nodes -L topology.kubernetes.io/zone
```

- Identify the current primary instance with the following command:

```bash
kubectl get -n <namespace> cluster/paradedb -o 'jsonpath={"Current Primary: "}{.status.currentPrimary}{"; Target Primary: "}{.status.targetPrimary}{"\n"}'
```

## Mitigation

1. Verify that there are two or more schedulable nodes per availability zone, with no taints preventing pod placement.

2. Verify your [affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/), taints, and tolerations configuration.

3. Delete pods and PVCs that are not in the desired availability zone. The CloudNativePG operator will automatically create replacement pods.

> [!IMPORTANT]
> Recreate pods one at a time, to avoid increasing the load on the primary instance. Before deleting, verify that:
>
> - You are connected to the correct cluster.
> - You are deleting the correct pod.
> - You are not deleting the active primary instance.

```bash
kubectl delete -n <namespace> pod/<pod-name> pvc/<pod-name> pvc/<pod-name>-wal
```
