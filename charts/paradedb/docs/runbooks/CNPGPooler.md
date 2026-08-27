# CNPGPooler

## Description

The `CNPGPoolerUnavailable` alert fires when a CloudNativePG-managed PgBouncer pooler has no available instances for five minutes. The `CNPGPoolerClientsWaiting` alert fires when clients remain queued for a server connection on a PgBouncer pod for five minutes.

PgBouncer is the customer-facing connection endpoint. PostgreSQL can remain healthy while pooler failures or saturation prevent customers from connecting.

## Impact

- An unavailable read-write pooler prevents new customer database connections.
- An unavailable read-only pooler prevents connections to the read endpoint.
- Sustained waiting clients experience increased connection and query latency and may time out.

## Diagnosis

Inspect the Pooler resource, deployment, pods, and recent events:

```bash
kubectl get -n <namespace> pooler,deploy,pod
kubectl describe -n <namespace> pooler/<pooler-name>
kubectl get events -n <namespace> --sort-by=.lastTimestamp
```

Check PgBouncer logs and current pool state:

```bash
kubectl logs -n <namespace> deployment/<pooler-name> --since=30m
kubectl exec -n <namespace> deployment/<pooler-name> -- psql pgbouncer -c "SHOW POOLS;"
```

If clients are waiting, determine whether PgBouncer has exhausted its server pool or PostgreSQL sessions are blocked. Check for database lock contention:

```sql
SELECT pid,
       pg_blocking_pids(pid) AS blocked_by,
       state,
       wait_event_type,
       wait_event,
       now() - xact_start AS transaction_age,
       query
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0
ORDER BY xact_start;
```

## Mitigation

For an unavailable pooler, correct scheduling, image, configuration, secret, or networking failures and allow CloudNativePG to restore the desired PgBouncer instances.

For waiting clients, resolve the limiting server pool or database bottleneck. Increase pool sizes only after confirming PostgreSQL has enough connection capacity. If a database transaction is blocking other sessions, terminate it only after confirming that rolling it back is safe.

Confirm afterward that the pooler has available replicas, `SHOW POOLS` reports no sustained client queue, customer connections succeed, and both alerts clear.
