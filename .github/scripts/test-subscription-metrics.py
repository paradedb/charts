#!/usr/bin/env python3
"""Exercise the actual exporter query against a disposable PostgreSQL instance.

Requires PyYAML and psql; uses PGHOST/PGPORT/PGUSER/PGPASSWORD. The supplied
YAML may be custom queries or a rendered ConfigMap containing custom-queries.
"""

import argparse
import json
import shlex
import subprocess
from pathlib import Path

import yaml

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('queries', type=Path)
parser.add_argument('--psql-command', default='psql')
args = parser.parse_args()
command = shlex.split(args.psql_command)


def sql(database, query):
    return subprocess.check_output(
        [*command, '-XAt', '-v', 'ON_ERROR_STOP=1', '-U', 'postgres', '-d', database, '-c', query],
        text=True,
    ).strip()


documents = list(yaml.safe_load_all(args.queries.read_text()))
queries = next(
    yaml.safe_load(doc['data']['custom-queries']) if doc.get('kind') == 'ConfigMap' else doc
    for doc in documents
    if doc and ('pg_stat_subscription' in doc or 'custom-queries' in doc.get('data', {}))
)
query = queries['pg_stat_subscription']['query'].strip().rstrip(';')
created = []
try:
    for database in ('subscription_metrics_a', 'subscription_metrics_b'):
        sql('postgres', f'CREATE DATABASE {database}')
        created.append(database)
        sql(database, """
            CREATE SUBSCRIPTION same_name CONNECTION 'host=invalid dbname=unused'
            PUBLICATION unused WITH (connect=false, enabled=false, create_slot=false, slot_name=NONE);
        """)
    for database in [*created, 'postgres']:
        result = json.loads(sql(database, f'SELECT COALESCE(json_agg(q), \'[]\'::json) FROM ({query}) q'))
        assert len(result) == (1 if database in created else 0), (database, result)
        for row in result:
            assert row['datname'] == database, row
            assert row['subname'] == 'same_name', row
            assert row['enabled'] is False, row
            assert row['pid'] is None, row
    print('Subscription query: correct database ownership, same-name isolation, disabled/no-worker visibility')
finally:
    for database in created:
        sql(database, 'DROP SUBSCRIPTION IF EXISTS same_name')
        sql('postgres', f'DROP DATABASE {database}')
