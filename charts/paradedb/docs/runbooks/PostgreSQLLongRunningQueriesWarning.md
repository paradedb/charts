# PostgreSQLLongRunningQueriesWarning

## Description

The `PostgreSQLLongRunningQueriesWarning` alert is triggered when the primary instance of a CloudNativePG cluster has a query that has been running for more than two hours.

The alert reads only the **primary**. Long-running reads on a standby are expected — that is often what standbys are for — and would otherwise page constantly on read-heavy replicas.

## Impact

A long-running query is not a problem in itself. An analytical query or an index build can legitimately run for hours. What makes it worth alerting on is what a long-running transaction holds open:

- **It holds back `xmin`**, so autovacuum cannot clean up dead tuples newer than the transaction's snapshot. Bloat accumulates across the whole database, not just the tables the query touches.
- **It may hold locks** that block DDL, and anything queueing behind that DDL, producing a stall far away from the query itself.
- **On a standby, it can delay replay** where `hot_standby_feedback` is on, which surfaces as physical replication lag.

The second-order effects usually arrive before anyone notices the query.

## Diagnosis

Find what is actually running, longest first:

```sql
SELECT pid,
       now() - query_start AS duration,
       state,
       wait_event_type,
       wait_event,
       left(query, 200) AS query
FROM pg_stat_activity
WHERE state <> 'idle'
  AND query_start < now() - interval '2 hours'
ORDER BY query_start;
```

Two cases look identical on the dashboard and need opposite responses:

- **`state = 'active'`** — the query is genuinely working. It may just be slow, or under-indexed.
- **`state = 'idle in transaction'`** — nothing is executing, but the transaction is open and still holding its snapshot and locks. This is almost always an application that opened a transaction and did not commit, and it is the more damaging of the two.

Check whether anything is blocked behind it:

```sql
SELECT pid, pg_blocking_pids(pid) AS blocked_by, left(query, 120)
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
```

## Mitigation

For a genuinely slow query, the fix is the query — check its plan and whether it has the indexes it needs.

For `idle in transaction`, the fix is the application: something is not committing or rolling back. Consider setting `idle_in_transaction_session_timeout` so the database bounds this itself rather than relying on an alert.

To cancel a query without dropping the connection:

```sql
SELECT pg_cancel_backend(<pid>);
```

Use `pg_terminate_backend(<pid>)` only if cancelling does not work — it drops the connection, which the application must be able to handle.

Before cancelling anything, check it is not a maintenance operation someone started deliberately. A cancelled `CREATE INDEX CONCURRENTLY` leaves an invalid index behind that has to be dropped by hand.
