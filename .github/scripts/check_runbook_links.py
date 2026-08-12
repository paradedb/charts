#!/usr/bin/env python3
"""Check that alert rules and runbooks agree with each other.

Two failure modes have bitten this repository, both silently:

  * a rule points at a runbook that does not exist, because the runbook was
    renamed or merged into another one and the rule was not updated;
  * a runbook exists that no rule points at, so nobody is ever sent to it.

Runbooks listed in EXTERNALLY_REFERENCED are documented here rather than
referenced by a rule in this repository. Keep that list short and explain
each entry.
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
RULES = ROOT / "charts/paradedb/prometheus_rules"
RUNBOOKS = ROOT / "charts/paradedb/docs/runbooks"

# Runbook -> why no rule in this repository points at it.
EXTERNALLY_REFERENCED = {
    "CNPGBackupFailed.md": (
        "alert lives in paradedb/mcc; needs kube_customresource_* series that "
        "the chart does not install"
    ),
    "CNPGScheduledBackupStalled.md": (
        "alert lives in paradedb/mcc; needs kube_customresource_* series that "
        "the chart does not install"
    ),
}

RUNBOOK_URL = re.compile(r"runbooks/(?P<name>(?:\{\{[^}]*\}\}|[^\s\"'])+\.md)")
ALERT_NAME = re.compile(r"\$alert\s*:=\s*\"(?P<name>[^\"]+)\"")


def main() -> int:
    errors: list[str] = []
    referenced: set[str] = set()

    rule_files = sorted(RULES.glob("*.yaml"))
    if not rule_files:
        print(f"no rule files found under {RULES}", file=sys.stderr)
        return 1

    for path in rule_files:
        text = path.read_text()
        rel = path.relative_to(ROOT)

        alert = ALERT_NAME.search(text)
        alert_name = alert.group("name") if alert else path.stem

        urls = RUNBOOK_URL.findall(text)
        if not urls:
            errors.append(f"{rel}: {alert_name} has no runbook_url")
            continue

        for name in urls:
            if "{{" in name:
                errors.append(
                    f"{rel}: {alert_name} builds its runbook_url from a template "
                    f"({name}); name the file so a rename cannot pass silently"
                )
                continue
            referenced.add(name)
            if not (RUNBOOKS / name).is_file():
                errors.append(f"{rel}: {alert_name} points at {name}, which does not exist")

    for path in sorted(RUNBOOKS.glob("*.md")):
        if path.name in referenced or path.name in EXTERNALLY_REFERENCED:
            continue
        errors.append(
            f"{path.relative_to(ROOT)}: no alert rule points at this runbook. "
            f"Wire it up, delete it, or add it to EXTERNALLY_REFERENCED in {pathlib.Path(__file__).name}"
        )

    for name, reason in sorted(EXTERNALLY_REFERENCED.items()):
        if not (RUNBOOKS / name).is_file():
            errors.append(
                f"EXTERNALLY_REFERENCED lists {name} ({reason}), but no such runbook exists"
            )

    if errors:
        print("Runbook link check failed:\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(
        f"ok: {len(rule_files)} rules, {len(referenced)} runbooks referenced, "
        f"{len(EXTERNALLY_REFERENCED)} referenced only from paradedb/mcc"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
