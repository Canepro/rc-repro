# Official Rocket.Chat Kubernetes artifact and compatibility envelope

Research date: 2026-07-31
Decision ticket: [Canepro/rc-repro#2](https://github.com/Canepro/rc-repro/issues/2)

## Decision

The `microservices` preset should consume Rocket.Chat's official
`rocketchat/rocketchat` Helm chart from
`https://rocketchat.github.io/helm-charts`. Its source of truth is the
[RocketChat/helm-charts repository](https://github.com/RocketChat/helm-charts),
and the official deployment guide installs this exact repository and chart.
Rocket.Chat also states that Kubernetes with the official Helm chart is the
supported way to deploy its microservices; direct Docker microservice deployment
is not supported
([Kubernetes deployment guide](https://docs.rocket.chat/docs/deploy-with-kubernetes),
[microservices guide](https://docs.rocket.chat/docs/microservices)).

rc-repro should not copy the rendered manifests. It should:

1. pin an official chart version and package SHA-256;
2. set `image.tag` to the user's existing `--version` value;
3. set `microservices.enabled: true` explicitly;
4. let that pinned chart own NATS and its other subchart/component versions; and
5. refuse an unverified application/chart pairing by default.

This preserves one user-facing Rocket.Chat version while retaining a
reproducible upstream topology.

## Why the Helm chart, not Launchpad

Rocket.Chat also offers Launchpad as an end-to-end Kubernetes deployment
product. Its documented scope includes dependency verification, ingress,
certificates, monitoring, a Helm controller, and operators; the same page says
that `launchcontrol`, which ultimately deploys workspaces, is closed source
([Launchpad deployment guide](https://docs.rocket.chat/docs/deploy-with-launchpad)).
That is a broader substrate-management system than the artifact needed by an
rc-repro preset. The open Helm chart is inspectable, versioned, downloadable by
digest, and already exposes the microservice topology, so it is the appropriate
upstream boundary for rc-repro.

## What each version controls

Rocket.Chat documents the application version and Helm chart version as
independent: changing the application does not necessarily publish a chart, and
using an unpinned chart during an upgrade can introduce unrelated breaking
changes
([Understanding Helm chart versions](https://docs.rocket.chat/docs/deploy-with-kubernetes#understanding-helm-chart-versions)).

| Input or artifact | rc-repro treatment | Primary-source basis |
| --- | --- | --- |
| Rocket.Chat `--version` | Write the exact value to `image.tag`. | The official deployment and update instructions select the Rocket.Chat release through `image.tag` ([guide](https://docs.rocket.chat/docs/deploy-with-kubernetes#step-6-configure-rocketchat), [update instructions](https://docs.rocket.chat/docs/deploy-with-kubernetes#updating-rocketchat-on-kubernetes)). |
| Helm chart version | Resolve separately, then pass it to Helm's `--version`; never float to latest. | The guide warns that an unpinned `helm upgrade` can move to a chart with breaking changes ([guide](https://docs.rocket.chat/docs/deploy-with-kubernetes#understanding-helm-chart-versions)). |
| Chart package digest | Persist and verify the SHA-256 published in the official chart index. | The repository's [official `index.yaml`](https://rocketchat.github.io/helm-charts/index.yaml) publishes a digest for every package. |
| Rocket.Chat microservice image versions | Do not accept separate normal-user inputs. The chart applies the same `image.tag`, falling back to `Chart.appVersion`, to the central Rocket.Chat image and each service image. | The tagged chart's [image helper](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/templates/_helpers.tpl), [central deployment](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/templates/chat-deployment.yaml), [account](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/templates/microservices-account-deployment.yaml), [authorization](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/templates/microservices-authorization-deployment.yaml), [presence](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/templates/microservices-presence-deployment.yaml), and [DDP streamer](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/templates/microservices-ddp-streamer-deployment.yaml) all use that rule. |
| NATS and chart dependencies | Leave them owned by the pinned chart package. | The chart declares NATS as conditional on microservices and pins dependency releases in the packaged `Chart.lock`; chart 7.0.2 declares the dependency in its [tagged `Chart.yaml`](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/Chart.yaml), and the immutable [7.0.2 package](https://rocketchat.github.io/helm-charts/charts/rocketchat-7.0.2.tgz) contains the lock and vendored subcharts. |

The official chart index and release notes therefore provide associations, not
a general compatibility range. `Chart.appVersion` is the chart's default
application tag and the release normally links to that Rocket.Chat release
([chart 7.0.2 metadata](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/Chart.yaml),
[chart 7.0.2 release](https://github.com/RocketChat/helm-charts/releases/tag/rocketchat-7.0.2)).
Neither the chart metadata nor the deployment documentation publishes a
constraint such as “chart X supports Rocket.Chat A through B.” Treating an
arbitrary nearby chart as compatible would therefore be an rc-repro inference,
not an upstream guarantee.

## Conservative compatibility resolution

For a normal `rc-repro up --version V --preset microservices`:

1. Read rc-repro's checked-in compatibility data, not a mutable live “latest”
   result.
2. Select the highest stable official chart whose published `appVersion`
   exactly equals `V`.
3. Pin the chart version and official package digest.
4. Still set `image.tag=V` explicitly so the requested application version is
   recorded and applied uniformly.
5. Before deployment, verify that the package digest matches and that the
   central image plus the account, authorization, presence, and DDP streamer
   image tags exist.
6. If no exact pair exists, fail preflight with a useful unsupported-pair
   result. Admit a non-exact pair only through a checked-in rc-repro
   compatibility entry backed by an end-to-end smoke test. An explicit advanced
   chart override may bypass selection, but must be reported as unverified
   unless that pair is already in the table.

This is deliberately stricter than the official update walkthrough, which
allows changing `image.tag` while using the newest chart but warns that the
chart may change independently
([update instructions](https://docs.rocket.chat/docs/deploy-with-kubernetes#updating-rocketchat-on-kubernetes)).
The stricter policy is an rc-repro reproducibility decision, not a claim that
other combinations cannot work.

### Initial exact-pair seed

As of 2026-07-31, the official
[`index.yaml`](https://rocketchat.github.io/helm-charts/index.yaml) contains the
following highest chart version for each 8.x `appVersion` association:

| Rocket.Chat `--version` | Pinned chart | Published package SHA-256 | Evidence |
| --- | --- | --- | --- |
| `8.6.1` | `7.0.2` | `be4b8c61a47d636ffe2cc3a22fc35e242583cd80b2601b7b49ecc457c1ae9fc2` | [release](https://github.com/RocketChat/helm-charts/releases/tag/rocketchat-7.0.2) |
| `8.5.0` | `7.0.0` | `cb9939a2341b881797ebd9cf4afa2868c7825b42eb19b969a2a6060f23cd4180` | [release](https://github.com/RocketChat/helm-charts/releases/tag/rocketchat-7.0.0) |
| `8.2.0` | `6.32.1` | `725b54b9f387cf777be6dd34297e70d933b1c0fcdf0c4e73d8fd2194ae38876b` | [release](https://github.com/RocketChat/helm-charts/releases/tag/rocketchat-6.32.1) |
| `8.1.0` | `6.31.0` | `e9a382459a5ed0577784029ffa3b48f34cd3bb084fa5c5ff1e069c8425dca3ff` | [release](https://github.com/RocketChat/helm-charts/releases/tag/rocketchat-6.31.0) |
| `8.0.1` | `6.30.0` | `a05991cd34cb4299ad241e21a4b67ed95b0614da294b050ddf025236ac1108a5` | [release](https://github.com/RocketChat/helm-charts/releases/tag/rocketchat-6.30.0) |
| `8.0.0` | `6.28.0` | `7876c5851dbc6255999a632b174885664724058304da35d5fdc07769fd563c52` | [release](https://github.com/RocketChat/helm-charts/releases/tag/rocketchat-6.28.0) |

There is no exact official index association for Rocket.Chat 8.3.x or 8.4.x in
that snapshot. Those versions require a separately tested rc-repro mapping;
choosing 6.32.x or 7.0.x merely because it is adjacent would be unsupported
guesswork. The mapping generator should also retain the published digest, not
only the two version strings.

## Values rc-repro must make explicit

The preset should explicitly own all behavior that affects reproducibility:

- `image.repository` and exact `image.tag`;
- `microservices.enabled: true`;
- `microservices.streamHub.enabled: false` for the initial 8.x envelope;
- MongoDB mode and connection source;
- NATS mode;
- ingress/service exposure;
- persistence and storage class; and
- generated release and namespace names.

The initial preset should use one replica per Rocket.Chat microservice. The
official deployment guide describes that shape as suitable for Community
workspaces and directs users who want multiple replicas to the scaling guide
([configuration guidance](https://docs.rocket.chat/docs/deploy-with-kubernetes#step-6-configure-rocketchat)).
Scaling or other license-dependent behavior should remain an explicit advanced
choice rather than a default assumption.

Explicit values are necessary because the tagged 7.0.2 sources disagree about
some defaults: its
[`values.yaml`](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/values.yaml)
sets `microservices.enabled: true` and omits `image.tag`, while its
[`README.md`](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/README.md)
documents microservices as defaulting to false and shows a stale image-tag
default. The templates, not that generated table, show that an omitted tag falls
back to `Chart.appVersion`
([helper](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/templates/_helpers.tpl)).

The current Kubernetes guide deploys MongoDB separately with the MongoDB
Community Operator and says the bundled Bitnami MongoDB setup is being retired
([deployment architecture and repository setup](https://docs.rocket.chat/docs/deploy-with-kubernetes)).
Therefore, the first self-contained rc-repro preset may use only a chart version
whose bundled database path has been proven in its disposable cluster, and its
design must not assume that bundled MongoDB remains available in future chart
releases.

## Cluster and tool envelope

The official deployment guide requires Helm 3, a configured Kubernetes cluster
with `kubectl` 1.21 or newer, and dynamic persistent-volume provisioning
([prerequisites](https://docs.rocket.chat/docs/deploy-with-kubernetes#prerequisites)).
It specifically warns that Kind, K3s, and Minikube may lack a storage
provisioner. The chart's tagged
[`Chart.yaml`](https://github.com/RocketChat/helm-charts/blob/rocketchat-7.0.2/rocketchat/Chart.yaml)
does not declare a `kubeVersion` constraint, so rc-repro cannot delegate that
preflight to Helm metadata.

For an rc-repro-owned local cluster, the implementation must consequently test
for a default StorageClass and successful dynamic claim binding before it starts
the Helm release. Meeting the documented CLI versions alone is insufficient.

## Acceptance proof required for each mapping

A mapping should be marked supported only after an isolated run proves:

1. the official chart package digest;
2. successful render and install with the exact checked-in values;
3. all central and microservice Deployments become available;
4. the Rocket.Chat HTTP readiness endpoint reports the requested version;
5. NATS-backed service connectivity is healthy;
6. evidence and logs can be collected through rc-repro; and
7. Helm release, namespace, cluster-owned storage, and local cluster teardown
   leave no owned resources behind.

The official chart repository itself tests both monolith and microservices modes
on KWOK and Kind
([test infrastructure and CI](https://github.com/RocketChat/helm-charts#testing-infrastructure)).
That validates the chart's intended topology, but it does not replace
rc-repro's end-to-end test of each application/chart pair.

## Resolution

Use the official `rocketchat/rocketchat` chart directly. Model compatibility as
a pinned tuple:

```text
(rocket_chat_version, chart_version, chart_package_sha256)
```

The chart owns the matching Rocket.Chat service image tag and its locked
infrastructure dependencies. Seed support only from exact official
`appVersion` associations, then widen it with explicit, tested rc-repro entries.
Do not derive compatibility from chart proximity and do not float to the latest
chart at runtime.
