# CNPGClusterInstancesOnSameNode

## Description

The `CNPGClusterInstancesOnSameNode` alert is raised when two or more database pods are scheduled on the same node. This is not the expected behavior for CloudNativePG clusters, as each instance should run on a separate node to ensure high availability and fault tolerance.

This can be caused by insufficient nodes in the cluster or misconfigured scheduling rules, such as affinity, anti-affinity, and tolerations.

## Impact

This configuration can affect high availability, since the downtime of a node with multiple database pods will bring down all the database pods on the node.

## Diagnosis

List all database pods and their node assignments:

```bash
kubectl get pods -A -l "cnpg.io/podRole=instance" -o json | jq -r '["Namespace", "Pod", "Node"], ( .items[] | [.metadata.namespace, .metadata.name, .spec.nodeName]) | @tsv' | column -t
```

Describe the cluster and check the affinity and tolerations configuration:

```bash
kubectl describe --namespace <namespace> clusters.postgresql.cnpg.io/paradedb
```

Describe the pods:

```bash
kubectl describe pods -A -l "cnpg.io/podRole=instance"
```

## Mitigation

- Verify that you have more than a single node with no taint preventing pods from being scheduled on these nodes.

- Verify your [affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/), taints, and tolerations configuration.

- Increase the instance CPU and Memory resources so that a node can only fit a one instance.

For more information, please refer to the ["Scheduling"](https://cloudnative-pg.io/documentation/current/scheduling/) section of the documentation.
