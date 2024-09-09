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

Check the current and target primary pods for restarts, scheduling failures, storage errors, failed probes, or PostgreSQL startup errors. A failover can also remain stuck when a long-running query on the current primary cannot be cancelled, preventing the operator from completing the transition.

## Mitigation

Resolve the underlying pod, node, storage, networking, or PostgreSQL failure preventing CloudNativePG from completing recovery. Preserve the current cluster state and logs before deleting pods or changing the primary target.

Do not manually trigger another replica promotion or modify CloudNativePG status fields. A promotion is already in progress, and starting a second concurrent promotion can lead to data loss. If the operator cannot recover after the underlying failure is corrected, follow the CloudNativePG failover procedures or escalate with the cluster status, events, and instance logs.

Confirm afterward that `currentPrimary` and `targetPrimary` match, the failing timestamp is cleared, the write service accepts connections, and the alert resolves.
