# Contributing to ParadeDB Charts

Open pull requests against `dev`. Keep changes focused and explain how you validated them.
Follow the [Code of Conduct](CODE_OF_CONDUCT.md).

The chart lives in `charts/paradedb`. Check changes locally with:

```bash
helm lint charts/paradedb
helm template paradedb charts/paradedb
```

CI runs the Chainsaw integration tests in `charts/paradedb/test`, including rule rendering
and monitoring resource checks. Update the relevant fixtures when changing chart behavior.

Chart versions are managed by the release workflow. Leave `Chart.yaml` version bumps out
of regular pull requests.
