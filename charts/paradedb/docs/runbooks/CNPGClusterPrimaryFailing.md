# CNPGClusterPrimaryFailing

## Description

The `CNPGClusterPrimaryFailing` alert fires when CloudNativePG has reported a failing primary for more than five minutes and the condition then remains active for another five minutes. A successful promotion or brief primary transition does not trigger the alert.

## Impact

- The cluster may not have a stable writable primary.
- Applications can experience failed connections, interrupted transactions, or write unavailability.
- Automatic failover or switchover recovery is not completing within the expected window.

## Diagnosis

Inspect the cluster status and conditions:

```bash
kubectl describe -n <namespace> cluster/<cluster-name>
kubectl get -n <namespace> cluster/<cluster-name> -o yaml
```

Compare `status.currentPrimary` with `status.targetPrimary`, then inspect recent cluster events and operator logs:

```bash
kubectl get events -n <namespace> --sort-by=.lastTimestamp
kubectl logs -n cnpg-system deployment/cnpg-controller-manager --since=30m
```

Check the current and target primary pods for restarts, scheduling failures, storage errors, failed probes, or PostgreSQL startup errors.

## Mitigation

Resolve the underlying pod, node, storage, networking, or PostgreSQL failure preventing CloudNativePG from completing recovery. Preserve the current cluster state and logs before deleting pods or changing the primary target.

Do not manually promote a replica or modify CloudNativePG status fields. If the operator cannot recover after the underlying failure is corrected, follow the CloudNativePG failover procedures or escalate with the cluster status, events, and instance logs.

Confirm afterward that `currentPrimary` and `targetPrimary` match, the failing timestamp is cleared, the write service accepts connections, and the alert resolves.
