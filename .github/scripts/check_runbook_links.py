#!/usr/bin/env python3
"""Check that every alert rule links to a runbook that exists in this repository.

A rule and the runbook it points at are edited separately, so a link breaks quietly:
the rule renders, the alert fires, and the on-call follows a 404 at the worst moment.

The rules are Helm templates rather than plain YAML, so they are read with a regex.
That is enough here — the alert name and the runbook link are both literals.

Note this deliberately does not flag runbooks that nothing links to. The MCC has its
own rules against these same runbooks, and it is private, so this repository cannot
see the full set of references. That check lives there instead.

Usage: check_runbook_links.py
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2] / "charts" / "paradedb"
RULES = ROOT / "prometheus_rules"
RUNBOOKS = ROOT / "docs" / "runbooks"
PREFIX = "https://github.com/paradedb/charts/blob/main/charts/paradedb/docs/runbooks/"

ALERT = re.compile(r'\$alert\s*:=\s*"([^"]+)"')
LINK = re.compile(r"runbook_url:\s*(\S+)")


def main():
    problems = []
    checked = 0

    for path in sorted(RULES.glob("*.yaml")):
        text = path.read_text()
        alert = ALERT.search(text)
        name = alert.group(1) if alert else path.name

        link = LINK.search(text)
        if not link:
            problems.append(f"{name}: no runbook_url")
            continue

        url = link.group(1)
        if not url.startswith(PREFIX):
            problems.append(f"{name}: runbook_url does not point at this repository's runbooks: {url}")
            continue

        runbook = RUNBOOKS / url[len(PREFIX):]
        if not runbook.is_file():
            problems.append(f"{name}: runbook does not exist: {runbook.relative_to(ROOT.parent.parent)}")
        checked += 1

    print(f"checked {checked} rules against {len(list(RUNBOOKS.glob('*.md')))} runbooks")
    for problem in problems:
        print(f"::error::{problem}")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
