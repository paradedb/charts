# CNPGClusterInstancesOnSameNode

## Description

The `CNPGClusterInstancesOnSameNode` alert is triggered when two or more database pods are scheduled on the same node. This is unexpected for CloudNativePG clusters, as each instance should run on a separate node to ensure high availability and fault tolerance.

This can be caused by insufficient nodes in the cluster or misconfigured scheduling rules, such as pod affinity/anti-affinity rules or tolerations.

## Impact

This configuration reduces high availability, as the failure of a node hosting multiple database pods will take all of them down at once.

## Diagnosis

To investigate node placement of database pods:

- List all database pods and their node assignments:

```bash
kubectl get -n <namespace> pods -l "cnpg.io/podRole=instance" -o json | jq -r '["Namespace", "Pod", "Node"], ( .items[] | [.metadata.namespace, .metadata.name, .spec.nodeName]) | @tsv' | column -t
```

- Describe the cluster and check the affinity and tolerations configuration:

```bash
kubectl describe -n <namespace> cluster/paradedb
```

- Describe the pods:

```bash
kubectl describe -n <namespace> pods -l "cnpg.io/podRole=instance"
```

## Mitigation

1. Verify that there are two or more schedulable nodes, with no taints preventing pod placement.

2. Verify your [affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/), taints, and tolerations configuration.

3. Increase the instance CPU and memory resources so that no node can host more than one instance.

For more details, see the [Scheduling](https://cloudnative-pg.io/documentation/current/scheduling/) section of the CloudNativePG documentation.
