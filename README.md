<h1 align="center">
  <a href="https://paradedb.com">
    <picture align=center>
      <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/paradedb/paradedb/main/docs/logo/paradedb-logo-dark-large.svg">
      <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/paradedb/paradedb/main/docs/logo/paradedb-logo-light-large.svg">
      <img alt="The ParadeDB logo." src="https://raw.githubusercontent.com/paradedb/paradedb/main/docs/logo/paradedb-logo-light-large.svg">
    </picture>
  </a>
  <br>
</h1>

<p align="center">
  <b>Search without a second system.</b><br/>
  One Postgres for your application data, full-text search, vector retrieval, and aggregations.
</p>

<h3 align="center">
  <a href="https://paradedb.com">Website</a> &bull;
  <a href="https://docs.paradedb.com">Docs</a> &bull;
  <a href="https://paradedb.com/slack">Community</a> &bull;
  <a href="https://paradedb.com/blog/">Blog</a> &bull;
  <a href="https://docs.paradedb.com/changelog/">Changelog</a>
</h3>

<p align="center">
  <a href="https://github.com/paradedb/charts/actions/workflows/paradedb-publish-chart.yml"><img src="https://github.com/paradedb/charts/actions/workflows/paradedb-publish-chart.yml/badge.svg" alt="Publish Helm Chart"></a>&nbsp;
  <a href="https://artifacthub.io/packages/search?repo=paradedb"><img src="https://img.shields.io/endpoint?url=https://artifacthub.io/badge/repository/paradedb" alt="Artifact Hub"></a>&nbsp;
  <a href="https://hub.docker.com/r/paradedb/paradedb"><img src="https://img.shields.io/docker/pulls/paradedb/paradedb" alt="Docker Pulls"></a>&nbsp;
  <a href="https://github.com/paradedb/charts/blob/main/LICENSE"><img src="https://img.shields.io/github/license/paradedb/charts?color=blue" alt="License"></a>&nbsp;
  <a href="https://paradedb.com/slack"><img src="https://img.shields.io/badge/Community-Join%20Slack-purple?logo=slack" alt="Community"></a>&nbsp;
  <a href="https://x.com/paradedb"><img src="https://img.shields.io/twitter/follow/paradedb" alt="Follow @paradedb"></a>
</p>

---

# ParadeDB Helm Chart

[ParadeDB](https://github.com/paradedb/paradedb) adds Elastic-quality full-text search, vector retrieval, and aggregations to Postgres with the `pg_search` extension. Your application data and your search engine live in one database, with no second system to deploy and nothing to sync.

The ParadeDB Helm Chart is based on the official [CloudNativePG Helm Chart](https://cloudnative-pg.io/). CloudNativePG is a Kubernetes operator that manages the full lifecycle of a highly available PostgreSQL database cluster with a primary/standby architecture using Postgres streaming (physical) replication.

Kubernetes, and specifically the CloudNativePG operator, is the recommended approach for deploying ParadeDB in production, with high availability. ParadeDB also provides a [Docker image](https://hub.docker.com/r/paradedb/paradedb) and [prebuilt binaries](https://github.com/paradedb/paradedb/releases) for Debian, Ubuntu, Red Hat Enterprise Linux, and macOS.

The ParadeDB Helm Chart supports Postgres 15+ and ships with Postgres 18 by default.

The chart is also available on [Artifact Hub](https://artifacthub.io/packages/helm/paradedb/paradedb).

## Usage

First, install [Helm](https://helm.sh/docs/intro/install/). The following steps assume you have a Kubernetes cluster running v1.29+. If you are testing locally, we recommend using [Minikube](https://minikube.sigs.k8s.io/docs/start/).

#### Monitoring

The ParadeDB Helm chart supports monitoring via Prometheus and Grafana. To enable monitoring, you need to have the Prometheus CRDs installed before installing the CloudNativePG operator. The Prometheus CRDs can be found [here](https://prometheus-community.github.io/helm-charts).

#### Installing the CloudNativePG Operator

Skip this step if the CloudNativePG operator is already installed in your cluster. For advanced CloudNativePG configuration and monitoring, please refer to the [CloudNativePG Cluster Chart documentation](https://github.com/paradedb/charts/blob/main/charts/cloudnative-pg/README.md#values).

```bash
helm repo add cnpg https://cloudnative-pg.github.io/charts
helm upgrade --atomic --install cnpg \
--create-namespace \
--namespace cnpg-system \
cnpg/cloudnative-pg
```

#### Setting up a ParadeDB CNPG Cluster

> [!IMPORTANT]
> When deploying a cluster with more than one instance, you must use `type: paradedb-enterprise` to enable replication of BM25 indexes across instances.
> Using ParadeDB Enterprise requires an access token. To request one, please [contact sales](mailto:sales@paradedb.com).

Create a `values.yaml` and configure it to your requirements. Here is a basic example:

```yaml
type: paradedb
mode: standalone

version:
  # -- PostgreSQL major version to use
  postgresql: "18"
  # -- ParadeDB version to use
  paradedb: "0.24.3"

cluster:
  instances: 1
  storage:
    size: 256Mi
```

Then, launch the ParadeDB cluster.

```bash
helm repo add paradedb https://paradedb.github.io/charts
helm upgrade --atomic --install paradedb \
--namespace paradedb \
--create-namespace \
--values values.yaml \
paradedb/paradedb
```

If `--values values.yaml` is omitted, the default values will be used. For advanced ParadeDB configuration and monitoring, please refer to the [ParadeDB Chart documentation](https://github.com/paradedb/charts/tree/dev/charts/paradedb#values).

#### Connecting to a ParadeDB CNPG Cluster

You can launch a Bash shell inside a specific pod via:

```bash
kubectl exec --stdin --tty <pod-name> -n paradedb -- bash
```

The primary is called `paradedb-1`. The replicas are called `paradedb-2` onwards depending on the number of replicas you configured. You can connect to the ParadeDB database with `psql` via:

```bash
psql -d paradedb
```

## Development

To test changes to the Chart on a local Minikube cluster, follow the instructions from [Self Hosted](#self-hosted) replacing the `helm upgrade` step by the path to the directory of the modified `Chart.yaml`.

```bash
helm upgrade --atomic --install paradedb --namespace paradedb --create-namespace ./charts/paradedb
```

## License

Apache-2.0 License - see [LICENSE](LICENSE) for details.
