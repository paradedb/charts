# Alert behavior tests

These fixtures evaluate the chart's rendered rules against synthetic metrics with
`vmalert-tool` v1.148.0. They cover scrape failures, missing collector metrics,
recovery, cluster isolation, configured standby counts, logical worker state,
and physical WAL backlog. Rendering checks run separately through Chainsaw.

Run locally from the repository root with Helm and `vmalert-tool` installed:

```sh
work=$(mktemp -d)
for instances in 1 2 3 4; do
  helm template alerts charts/paradedb \
    --namespace alert-test \
    --set "cluster.instances=$instances" \
    --set cluster.monitoring.enabled=true \
    --set cluster.monitoring.prometheusRule.enabled=true \
    --show-only templates/prometheus-rule.yaml \
    | sed '1,/^spec:$/d' > "$work/rules-$instances.yaml"
done
cp tests/alert-rules/*_test.yaml "$work/"
(cd "$work" && vmalert-tool unittest --disableAlertgroupLabel --files='*_test.yaml')
```

PostgreSQL version checks for index usage metrics run in the Chainsaw
`prometheus-rule-rendering` test.
