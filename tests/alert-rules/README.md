# Alert behavior tests

These fixtures evaluate the chart's rendered rules against synthetic metrics with
`vmalert-tool` v1.148.0. They cover scrape failures, missing collector metrics,
recovery, cluster isolation, configured standby counts, logical worker state,
and physical WAL backlog. Rendering checks run separately through Chainsaw.

The `Test Alert Rules` workflow renders one-, two-, three-, and four-instance
clusters into a temporary directory and runs the fixtures with `vmalert-tool`.
Its shell commands can also be run locally with Helm and `vmalert-tool` installed.

PostgreSQL version checks for index usage metrics run in the Chainsaw
`prometheus-rule-rendering` test.
