CNPGClusterInstancesOnSameNode
============================

Meaning
-------

The `CNPGClusterInstancesOnSameNode` alert is raised when two or more database pods are scheduled on the same node. This
is not the expected behavior for CloudNativePG clusters, as each instance should run on a separate node to ensure high
availability and fault tolerance.

This can be caused by insufficient nodes in the cluster or misconfigured scheduling rules, such as affinity, anti-affinity,
and tolerations.

Impact
------

Normally, no two CloudNativePG cluster instances should be scheduled on the same node. High availability is affected because
if the node on which the instances are scheduled fails, all instances will become unavailable.

Diagnosis
---------

List all database pods and their node assignments:

```bash
kubectl get pods -A -l "cnpg.io/podRole=instance" -o json | jq -r '["Namespace", "Pod", "Node"], ( .items[] | [.metadata.namespace, .metadata.name, .spec.nodeName]) | @tsv' | column -t
```

Describe the cluster and check the affinity and tolerations configuration:

```bash
kubectl describe --namespace NAMESPACE clusters.postgresql.cnpg.io/paradedb
```

Describe the pods:

```bash
kubectl describe pods -A -l "cnpg.io/podRole=instance"
```

Mitigation
----------

1. Verify you have more than a single node with no taints preventing pods from being scheduled there.
2. Verify your [affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/), taints, and tolerations configuration.
3. Increase the instance CPU and Memory resources such that only one instance can fit on a single node.
4. For more information, please refer to the ["Scheduling"](https://cloudnative-pg.io/documentation/current/scheduling/) section in the documentation
