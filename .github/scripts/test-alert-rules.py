#!/usr/bin/env python3
"""Render Helm rules and run the alert behavior fixtures with vmalert-tool."""

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vmalert-tool', default='vmalert-tool')
    parser.add_argument('--chart-dir', type=Path, default=ROOT / 'charts/paradedb')
    args = parser.parse_args()
    # last_idx_scan is available in PostgreSQL 16 and later.
    for version in (14, 15, 16, 17, 18):
        rendered = subprocess.check_output([
            'helm', 'template', 'metrics', str(args.chart_dir),
            '--set-string', f'version.postgresql={version}',
            '--show-only', 'templates/monitoring-paradedb-index.yaml',
        ], text=True)
        config = yaml.safe_load(yaml.safe_load(rendered)['data']['custom-queries'])
        usage = config['paradedb_index_usage']
        assert ('s.last_idx_scan' in usage['query']) == (version >= 16)
        assert any('last_idx_scan' in metric for metric in usage['metrics']) == (version >= 16)
        assert 'pdb.' not in usage['query'], 'Usage collection must not open index storage'
    fixtures = ROOT / 'tests/alert-rules'
    with tempfile.TemporaryDirectory(prefix='charts-alert-rules-') as directory:
        work = Path(directory)
        for instances in (1, 2, 3, 4):
            rendered = subprocess.check_output([
                'helm', 'template', 'alerts', str(args.chart_dir),
                '--namespace', 'alert-test',
                '--set', f'cluster.instances={instances}',
                '--set', 'cluster.monitoring.enabled=true',
                '--set', 'cluster.monitoring.prometheusRule.enabled=true',
                '--show-only', 'templates/prometheus-rule.yaml',
            ], text=True)
            document = yaml.safe_load(rendered)
            (work / f'rules-{instances}.yaml').write_text(yaml.safe_dump(document['spec']))
        for fixture in fixtures.glob('*_test.yaml'):
            shutil.copy(fixture, work)
        subprocess.run([
            args.vmalert_tool, 'unittest', '--disableAlertgroupLabel',
            '--files=*_test.yaml',
        ], cwd=work, check=True)


if __name__ == '__main__':
    main()
