# CNPGClusterOffline

## Description

The `CNPGClusterOffline` alert is triggered when no CloudNativePG instances are ready.

## Impact

When the cluster is offline, applications cannot access the database, resulting in a full service disruption.

## Diagnosis

To investigate why the cluster is offline:

- Get the status of the CloudNativePG cluster instances:

```bash
kubectl get -n <namespace> pods -l "cnpg.io/podRole=instance" -o wide
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

For more details, see the [CloudNativePG Failure Modes](https://cloudnative-pg.io/documentation/current/failure_modes/) and [CloudNativePG Troubleshooting](https://cloudnative-pg.io/documentation/current/troubleshooting/) documentation.
