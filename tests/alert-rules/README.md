# Alert behavior tests

These fixtures evaluate the chart's rendered rules against synthetic metrics with
`vmalert-tool` v1.148.0. They cover scrape failures, missing collector metrics,
recovery, cluster isolation, configured standby counts, logical worker state,
and physical WAL backlog. Rendering checks run separately through Chainsaw.

Run from the repository root with Helm, Python, PyYAML and `vmalert-tool` installed:

```sh
python3 .github/scripts/test-alert-rules.py
```

Use `--vmalert-tool /path/to/vmalert-tool-prod` for a binary outside `PATH`.
The script renders one-, two-, three-, and four-instance clusters into a temporary
directory and removes the generated files when it finishes.
