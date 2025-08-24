CNPGClusterLowDiskSpaceWarning
==============================

Meaning
-------

This alert is triggered when the disk space usage on the CloudNativePG cluster exceeds 90%. It can be triggered by either:

* the PVC hosting the `PGDATA` (`storage` section)
* the PVC hosting WAL files (`walStorage` section), where applicable
* any PVC hosting a tablespace (`tablespaces` section)

Impact
------

Reaching 100% disk usage will result in downtime and data loss.

Moreover, very high disk space usage can lead to disk fragmentation, where files are split due to the absence of large-enough contiguous blocks of available storage, significantly increasing random I/O and degrading performance. Disk fragmentation can start happening at ~80% disk space usage.

Diagnosis
---------

Use the [CloudNativePG Grafana Dashboard](https://grafana.com/grafana/dashboards/20417-cloudnativepg/).

Mitigation
----------

* If you experience issues with the WAL (Write-Ahead Logging) volume and have set up continuous archiving, ensure that WAL archiving is functioning correctly. This is crucial to avoid a buildup of WAL files in the `pg_wal` folder. Monitor the `cnpg_collector_pg_wal_archive_status` metric, specifically ensuring that the number of `ready` files does not increase linearly.

* Refer to this documentation for more information on how to [Resize the CloudNativePG Cluster Storage](https://cloudnative-pg.io/documentation/current/troubleshooting/#storage-is-full).

* If using the ParadeDB BYOC Terraform module, refer to the `docs/handbook/NotEnoughDiskSpace.md` handbook to increase the disk space of the CloudNativePG cluster instances. This will require a restart of the ParadeDB and a primary switchover, which will cause a brief service disruption.
