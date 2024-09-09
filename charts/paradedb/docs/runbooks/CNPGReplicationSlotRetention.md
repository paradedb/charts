# CNPGReplicationSlotRetention

## Description

The `CNPGReplicationSlotInactive` alert fires when a replication slot on the primary has been inactive while retaining WAL for at least 15 minutes. The `CNPGReplicationSlotHighRetention` alert fires when a slot retains more than 25% of the volume that stores WAL for at least 15 minutes.

PostgreSQL retains every WAL segment required by a replication slot until its consumer advances the slot. An abandoned logical subscriber or a disconnected physical replica can therefore fill the volume indefinitely, at which point PostgreSQL stops accepting writes.

## Impact

- WAL storage grows until the affected consumer reconnects, advances, or the slot is removed.
- Backups and healthy replicas do not release WAL retained for another slot.
- If the volume fills, PostgreSQL can no longer accept writes and may become unavailable.

## Diagnosis

Inspect non-temporary slots on the primary:

```sql
SELECT slot_name,
       slot_type,
       database,
       active,
       active_pid,
       restart_lsn,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots
WHERE NOT temporary
ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC NULLS LAST;
```

For a logical slot, identify the subscription or external CDC consumer that owns `slot_name`. For a physical slot whose name begins with `_cnpg_`, inspect the corresponding CloudNativePG replica and its WAL receiver. Check recent consumer, network, and PostgreSQL logs before deciding that a slot is abandoned.

Confirm whether the cluster has dedicated WAL storage. A PVC ending in `-wal` stores retained WAL when present; otherwise WAL shares the instance's data PVC.

## Mitigation

Restore the intended consumer first. Once it reconnects and advances its confirmed or replay LSN, PostgreSQL will recycle the retained WAL automatically.

If a logical consumer has been permanently removed, verify that it cannot return and that its retained changes are no longer required, then drop its slot on the primary:

```sql
SELECT pg_drop_replication_slot('<slot_name>');
```

Dropping a slot is irreversible and forces that consumer to be reinitialized from a new snapshot or base backup. Do not manually drop CloudNativePG-managed `_cnpg_` physical slots; repair or remove the corresponding replica through CloudNativePG instead.

If the volume is close to full, add storage before recovery work so the database does not run out of space while the consumer catches up. Confirm afterward that the slot is active or gone, retained bytes are falling, and both alerts clear.
