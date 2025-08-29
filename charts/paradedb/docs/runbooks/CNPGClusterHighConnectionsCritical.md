# CNPGClusterHighConnectionsCritical

## Description

This alert is triggered when the number of connections to the CloudNativePG cluster instance exceeds 95% of its capacity.

## Impact

At 100% capacity, the CloudNativePG cluster instance will not be able to accept new connections. This will result in a service disruption.

## Diagnosis

Use the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/) to check the number of connections to the CloudNativePG cluster instances. Identify the instance that is experiencing issues and whether that instance is the primary or a standby replica.

You can check the current primary instance using the following command:

```bash
kubectl get cluster paradedb -o 'jsonpath={"Current Primary: "}{.status.currentPrimary}{"; Target Primary: "}{.status.targetPrimary}{"\n"}' --namespace <namespace>
```

## Mitigation

> [!IMPORTANT]
> Changing the `max_connections` parameter requires a restart of the CloudNativePG cluster instances. This will cause a restart of a standby instance and a switchover of the primary instance, causing a brief service disruption.

- Increase the maximum number of connections by increasing the `max_connections` PostgreSQL parameter.

- Use connection pooling by enabling PgBouncer to reduce the number of connections to the database.

- Increase the maximum number of connections by increasing the `max_connections` PostgreSQL parameter. You can do this by setting: `cluster.postgresql.parameters.max_connections` in your Helm values.

If using the ParadeDB BYOC Terraform module, set: `paradedb.postgresql.parameters.max_connections`.

- Use connection pooling by enabling PgBouncer to reduce the number of connections to the database. Note that PgBouncer also requires a set of connections, and you should make sure to increase the `max_connections` parameter temporarily while enabling PgBouncer to avoid service disruption.

> [!NOTE]
> PostgreSQL sizes certain resources directly based on the value of `max_connections`. Each connection uses
> a portion of the `shared_buffers` memory as well as additional non-shared memory. As a result, increasing the `max_connections` parameter will increase the memory usage of the CloudNativePG cluster instances.
