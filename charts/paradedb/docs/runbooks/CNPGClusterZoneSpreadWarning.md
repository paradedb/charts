CNPGClusterZoneSpreadWarning
============================

Meaning
-------

The `CNPGClusterZoneSpreadWarning` alert is raised when pods are not evenly distributed across availability zones. To be more accurate, the alert is raised when both of the following conditions are met:

* the number of pods exceeds the number of zones
* the number of zones is less than 3.

This can be caused by insufficient nodes in the cluster or misconfigured scheduling rules, such as affinity, anti-affinity, and tolerations.

Impact
------

The uneven distribution of pods across availability zones can lead to a single point of failure if a zone goes down.

Diagnosis
---------

Use the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/).

Get the status of the CloudNativePG cluster instances:

```bash
kubectl get pods -A -l "cnpg.io/podRole=instance" -o wide
```

Get the nodes and their respective zones:

```bash
kubectl get nodes --label-columns topology.kubernetes.io/zone
```

You can identify the current primary instance with the following command:

```bash
kubectl get cluster paradedb -o 'jsonpath={"Current Primary: "}{.status.currentPrimary}{"; Target Primary: "}{.status.targetPrimary}{"\n"}' --namespace NAMESPACE
```

Mitigation
----------

1. Verify you have more than a single node with no taints, preventing pods to be scheduled in each availability zone.

2. Verify your [affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/) and taints and tolerations configuration.

3. Delete the pods and their respective PVCs that are not in the desired availability zone and allow the operator to repair the cluster. Make sure you do this only one pod at a time to avoid increasing the load on the primary instance unnecessarily.

Very carefully verify that:

* You are deleting the correct pod.
* You are not deleting the active primary instance.

```bash
kubectl delete --namespace NAMESPACE pod/POD_NAME pvc/POD_NAME pvc/POD_NAME-wal
```
