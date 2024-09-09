# CNPGClusterOffline

## Description

The `CNPGClusterOffline` alert indicates no ready instances or missing collector metrics across the cluster, depending on the configured alert rule. Confirm database availability directly; missing metrics can also indicate an exporter or scrape failure.

## Impact

A database outage disrupts application traffic. An exporter or scrape outage leaves the cluster unmonitored while PostgreSQL may remain available.

## Diagnosis

Check application connectivity and the monitoring targets, then inspect the cluster:

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
