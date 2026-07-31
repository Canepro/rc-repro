# Rocket.Chat Kubernetes artifact and version compatibility envelope

Research ticket: [Canepro/rc-repro#2](https://github.com/Canepro/rc-repro/issues/2).
Wayfinder map: [Canepro/rc-repro#1](https://github.com/Canepro/rc-repro/issues/1).
Domain language: [`CONTEXT.md`](../CONTEXT.md).

Status: planning only. Nothing here was implemented.
Evidence gathered 2026-07-31 against the live chart index generated
`2026-07-30T12:22:36Z` (`index.yaml` `generated` field).

## Answer

The Microservices Preset should consume the official Helm chart
`rocketchat` from `https://rocketchat.github.io/helm-charts`
(source repo `https://github.com/RocketChat/helm-charts`), installed with
`microservices.enabled: true`, and rc-repro should map `--version` onto
`image.tag` rather than onto a chart version, because one `image.tag` value pins
the Rocket.Chat image *and* every microservice component image to the same tag.
Chart selection should be a **hybrid**: a live query of the published
`index.yaml` with a shipped static floor table as the offline fallback, mirroring
the two-tier pattern rc-repro already uses in `rc_repro/versions.py`.

Verified end to end: `helm template` against chart `rocketchat-7.0.2` with
`image.tag: "8.2.0"`, `microservices.enabled: true` and
`mongodb.image.tag: "8.0"` renders the full microservices topology with every
Rocket.Chat component at `8.2.0` and MongoDB at `8.0`, with no vendored
manifests. Render output is reproduced under [Verification](#verification).

## 1. The recommended artifact, and evidence it is official

| Item | Value |
| --- | --- |
| Helm repo URL | `https://rocketchat.github.io/helm-charts` |
| Chart name | `rocketchat` |
| Source repo | `https://github.com/RocketChat/helm-charts` |
| Latest chart version | `7.0.2` (appVersion `8.6.1`) |
| Chart apiVersion | `v2` |

Evidence that it is first-party:

- Rocket.Chat's own Kubernetes deployment documentation instructs
  `helm repo add rocketchat https://rocketchat.github.io/helm-charts` and
  deploying `rocketchat/rocketchat`
  ([docs.rocket.chat/docs/deploy-with-kubernetes](https://docs.rocket.chat/docs/deploy-with-kubernetes)).
  **Verified fact.**
- The GitHub repo is owned by the `RocketChat` organisation, described
  "Repository for RocketChat helm charts", not archived, default branch
  `master` (`gh api repos/RocketChat/helm-charts`). **Verified fact.**
- `Chart.yaml` of the packaged chart lists
  `maintainers: [{name: RocketChat, email: cloud@rocket.chat}]`,
  `home: https://rocket.chat/`, and
  `sources: [https://github.com/RocketChat/Docker.Official.Image/]`
  (`rocketchat/Chart.yaml` lines 29 to 34 in `rocketchat-7.0.2.tgz`).
  **Verified fact.**
- The default image repository is `registry.rocket.chat/rocketchat/rocket.chat`
  (chart `values.yaml:33`), which is byte-identical to rc-repro's own
  `default_rc_image` at `rc_repro/data/versions.yaml:16`. **Verified fact**, and
  a useful signal that the chart and rc-repro already agree on the image source.

The repo publishes three charts: `rocketchat` (95 releases), `rocketchat-voip`
(1 release), `monitoring` (17 releases). Only `rocketchat` is relevant.
**Verified fact** from parsing `index.yaml`.

Caveat: `gh api repos/RocketChat/helm-charts` returns `license: null`, so the
repository declares no SPDX license via the GitHub API. Could not verify a
license file exists. This matters only if rc-repro were to vendor chart content,
which the map forbids anyway.

## 2. Chart version to Rocket.Chat appVersion mapping

The chart tracks Rocket.Chat via `appVersion`, and the two version streams
diverged at chart `6.4.0`. Before that they were identical (chart `6.3.4` ->
appVersion `6.3.4`).

Recent mapping, from the published index (**verified fact**):

| Chart | appVersion (Rocket.Chat) |
| --- | --- |
| 7.0.2 | 8.6.1 |
| 7.0.1 | 8.6.1 |
| 7.0.0 | 8.5.0 |
| 6.32.1 | 8.2.0 |
| 6.32.0 | 8.2.0 |
| 6.31.0 | 8.1.0 |
| 6.30.0 | 8.0.1 |
| 6.28.0 | 8.0.0 |
| 6.27.1 | 7.11.0 |
| 6.26.0 | 7.10.0 |
| 6.25.3 | 7.9.3 |

Three properties of this mapping decide the resolution mechanism, all
**verified fact** by parsing all 95 index entries:

1. **Sparse.** 95 chart releases carry only **76 distinct appVersions**.
   Rocket.Chat ships far more releases than that, so an exact
   `appVersion == --version` match fails for most inputs. Verified misses:
   RC `8.4.0` -> no chart; RC `7.8.0` -> no chart.
2. **Non-monotonic.** appVersion decreases across a rising chart version at six
   points in history: chart `3.2.0`(4.2.1)->`3.3.0`(3.18.3),
   `6.3.4`(6.3.4)->`6.4.0`(6.3.3), `6.6.4`(6.6.1)->`6.6.5`(6.5.4),
   `6.9.4`(6.7.0)->`6.9.5`(6.5.6), `6.18.1`(6.11.1)->`6.18.2`(6.10.4),
   `6.20.0`(6.12.0)->`6.20.1`(6.9.6). So you cannot binary-search the index or
   assume "higher chart means newer Rocket.Chat".
3. **Many-to-one.** Several charts share one appVersion (`6.23.0`, `6.23.1`,
   `6.23.2` all -> `6.13.0`), so a match may return a set and needs a
   tie-break (highest chart version).

The `created` timestamp in `index.yaml` is **not** a release date: all 95
entries carry `2026-07-30T12:22:3x`, the index regeneration time. Real release
dates are only available from `gh api repos/RocketChat/helm-charts/releases`
(for example `rocketchat-7.0.0` published `2026-06-15T13:55:27Z`). **Verified
fact**, and a trap for any resolver that tries to order by `created`.

Rocket.Chat's own docs do not publish a Rocket.Chat-version-to-chart-version
table. Could not verify one exists. Inference: the mapping must be derived from
the index, not read from a doc.

## 3. How the microservices topology is enabled

`microservices.enabled: true`. **Verified fact** from three independent
first-party places:

- Chart `values.yaml:382-383` in `rocketchat-7.0.2`.
- The chart's own test fixture `rocketchat/tests/microservices-values.yaml`,
  which sets `microservices.enabled: true` alongside `image.tag:
  "${ROCKETCHAT_TAG}"`.
- Rocket.Chat docs ([deploy-with-kubernetes](https://docs.rocket.chat/docs/deploy-with-kubernetes),
  [microservices](https://docs.rocket.chat/docs/microservices)).

The components the flag switches on, from the rendered manifests: Deployments
`presence`, `ddp-streamer`, `account`, `authorization`, plus a NATS StatefulSet
and per-service Services. `TRANSPORTER` and `MOLECULER_LOG_LEVEL` are injected
into the monolith and each microservice. **Verified fact.**

Three behaviours worth pinning down:

- **The default flipped.** `microservices.enabled` defaults to `false` in charts
  up to `6.25.3` and to `true` from `6.28.0` onward (verified in `6.5.3`,
  `6.20.0`, `6.25.3` = false; `6.28.0`, `6.32.1`, `7.0.2` = true). rc-repro must
  therefore set the flag **explicitly in both directions**: `true` for the
  Microservices Preset and `false` for any monolith Kubernetes deployment, or
  the topology silently depends on which chart got selected.
- **The chart README contradicts the chart.** `rocketchat/README.md:130`
  documents `microservices.enabled` default `false` and `README.md:65`
  documents `image.tag` default `3.18.3`. Both are stale relative to
  `values.yaml`. **Verified fact.** Trust `values.yaml`, not the README.
- **NATS is conditional on it.** `Chart.yaml:12-15` declares the NATS dependency
  with `condition: nats.enabled, microservices.enabled`, and `values.yaml:462-470`
  documents that `nats.enabled` is nil by default so NATS deployment follows
  `microservices.enabled`. **Verified fact.**

### License gate

The chart's values file heads the microservices block with
"`Only available to E.E users`" (`values.yaml:376-378`), and the docs page
carries a Premium badge. **Verified fact** that microservices is a
Premium/Enterprise feature. `templates/_validations.yaml` does **not** fail a
license-less microservices install; only `nats.existingSecret` misuse is
validated. So the manifests render and the pods start, but licensing is enforced
by the Rocket.Chat app at runtime, not by Helm. **Inference** on the runtime
enforcement path: not exercised against a live cluster.

The chart accepts the license directly:
`license: ""` (`values.yaml:90-95`) is injected as `ROCKETCHAT_LICENSE` plus
`LICENSE_DEBUG` on the monolith Deployment (`templates/chat-deployment.yaml:105-111`)
and stored in the release Secret (`templates/secret.yaml:16-17`).
`registrationToken` is injected as `REG_TOKEN` on install only
(`chat-deployment.yaml:98-99`). This lines up with rc-repro's existing
`Spec.reg_token` (`rc_repro/compose.py:29`) and `Preset.requires_license`
(`rc_repro/presets/__init__.py:26`). The Microservices Preset should set
`requires_license=True`.

Note: the `license` value reaches only the monolith Deployment, not the
microservice Deployments. **Verified fact** from the grep above. Whether the
microservices need the license env themselves could not be verified.

## 4. Which component versions the chart controls, and which rc-repro must pin

### rc-repro pins (one value, `image.tag`)

`templates/_helpers.tpl:29` defines the shared image helper as
`{{- $tag := .tag | default .appVersion -}}`, and every Rocket.Chat workload
passes `.Values.image.tag` into it with its own repository. Confirmed at
`templates/chat-deployment.yaml:52` and
`templates/microservices-presence-deployment.yaml:49`. **Verified fact:** a
single `image.tag` pins the monolith and all four microservice images to the
same tag, overriding `Chart.AppVersion`.

That is the whole mapping rc-repro needs for the application tier. The
microservice images publish tags matching the Rocket.Chat version exactly.
Verified by HTTP 200 on `hub.docker.com/v2/repositories/rocketchat/<svc>/tags/<tag>`
for `presence-service`, `ddp-streamer-service`, `account-service`,
`authorization-service` at tags `8.6.1`, `8.5.0`, `8.2.0`, `7.9.3`, `6.13.0`,
`6.5.3`, `6.3.4`. **Verified fact.**

`stream-hub-service` is the exception: 404 at `8.2.0`, `8.5.0`, `8.6.1`; 200 at
`7.9.3` and below. **Verified fact**, and consistent with the chart's own note
that Stream Hub is "disabled by default as of Rocket.Chat 7.7.3 ... After
version 8.0.0, this service will be removed completely"
(`values.yaml:436-440`). The chart handles this itself:
`templates/_helpers.tpl:223-226` auto-enables Stream Hub when
`semverCompare "<=7.7.0" (.Values.image.tag | default .Chart.AppVersion)`.
Consequence for rc-repro: `image.tag` must be a **valid semver**, not `latest`
or a floating tag, or the chart's own version-conditional logic misfires.

### rc-repro must also pin MongoDB

The chart does **not** resolve MongoDB from the Rocket.Chat version, and says so
explicitly. It vendors Bitnami `mongodb` chart `13.18.5` (`Chart.lock:2-4`)
whose own `appVersion` is **`6.0.10`** (`charts/mongodb/Chart.yaml:16`), and the
Rocket.Chat chart sets `mongodb.image.repository: bitnamilegacy/mongodb`
(`values.yaml:133-135`) **with no tag**. The chart's own README states both
halves of this:

- "This chart defaults to mongodb 6.0.x as of the time of writing this"
  (`rocketchat/README.md:627`).
- "The chart will not check if the mongodb version is supported by the
  Rocket.Chat version ... It is up to the user to make sure of that."
  (`rocketchat/README.md:633`).

**Verified fact.** The README's documented override shape is
`mongodb.image.tag` (`rocketchat/README.md:640-641`), which is what the
verification render used.

So chart `7.0.2` (appVersion `8.6.1`) ships a default MongoDB of `6.0.x` while
Rocket.Chat 8.x requires MongoDB 8.0 per the releases API. rc-repro must set
`mongodb.image.tag` from its own `versions.resolve()` output
(`rc_repro/versions.py:119-148`), exactly as `compose.py:111` and
`compose.py:136` already do for Docker. This is the single biggest compatibility
gap and the strongest argument that rc-repro's existing resolver stays the
source of truth for MongoDB.

Two conveniences here. The chart already pins the Bitnami images into the
`bitnamilegacy/*` namespace (`values.yaml:135`, `:138`, `:143`, `:146`, `:150`,
`:195`), which is the identical workaround rc-repro applies at
`rc_repro/compose.py:111` and documents at `data/versions.yaml:8-11`. And the
chart sets `mongodb.architecture: replicaset` with `replicaCount: 1`
(`values.yaml:183-184`), so Rocket.Chat's replica-set requirement is met without
rc-repro doing anything. Both **verified fact**.

### The chart controls (rc-repro should not pin)

All **verified fact** from `values.yaml` / `Chart.lock` of `7.0.2`:

| Component | Pinned where | Value in chart 7.0.2 |
| --- | --- | --- |
| NATS server image | `values.yaml:485-486` | `nats:2.12-alpine` |
| NATS chart | `Chart.lock:8-10` | `0.15.1` (constraint `0.15.x`) |
| nats-box | `values.yaml:487-488` | `natsio/nats-box:0.19.2` |
| NATS config reloader | `values.yaml:493-494` | `natsio/nats-server-config-reloader:0.21.1` |
| NATS boot config | `values.yaml:495-496` | `natsio/nats-boot-config:0.21.1` |
| NATS exporter | `values.yaml:502-504` | `natsio/prometheus-nats-exporter:0.18.0` |
| MongoDB chart | `Chart.lock:2-4` | `13.18.5` (constraint `13.x.x`) |
| MongoDB exporter | `values.yaml:195` | `bitnamilegacy/mongodb-exporter` (tag from subchart) |
| PostgreSQL chart | `Chart.lock:5-7` | `15.5.38`, `postgresql.enabled: false` |
| Synapse (federation) | `values.yaml:509-513` | `matrixdotorg/synapse:v1.84.1`, disabled |

Because subcharts are vendored into the packaged `.tgz` (`charts/mongodb`,
`charts/nats`, `charts/postgresql` all present in `rocketchat-7.0.2.tgz`) and
`Chart.lock` fixes exact versions at package time, installing a specific chart
version is deterministic for every dependency. **Verified fact.** rc-repro does
not need to pin NATS at all, which is a simplification over the Docker path,
where `rc_repro/presets/multi_instance.py:29` hand-pins `nats:2.11-alpine`.

## 5. Recommended mechanism for resolving `--version` to a chart version

**Recommendation: hybrid.** Live query of `index.yaml` as the primary path, a
shipped static floor table as the offline fallback. This is not a new pattern in
rc-repro; it is the pattern `rc_repro/versions.py:1-11` already documents for
MongoDB ("Two tiers: LIVE ... FALLBACK") and implements at
`versions.py:129-146`.

Resolution algorithm, all three steps grounded in the properties verified in
section 2:

1. `GET https://rocketchat.github.io/helm-charts/index.yaml`. Verified reachable
   without auth or a Helm binary: HTTP 200, 118845 bytes, `apiVersion: v1`.
   rc-repro already depends on `requests` (`versions.py:19`), so this needs no
   new dependency and no `helm repo add`.
2. Prefer an exact `appVersion == --version` match; among ties take the highest
   chart version. Verified to work for RC `8.6.1` (-> chart `7.0.2`), `8.2.0`
   (-> `6.32.1`), `7.9.3` (-> `6.25.3`), `6.5.3` (-> `6.5.3`).
3. On a miss, fall back to a **floor**: the entry with the highest `appVersion`
   that is still `<= --version`, then the highest chart version among ties.
   Verified outcomes: RC `8.4.0` -> chart `6.32.1` (appVersion `8.2.0`);
   RC `7.8.0` -> chart `6.25.2` (appVersion `7.6.0`); RC `6.10.0` -> chart
   `6.17.0` (appVersion `6.10.0`). The floor must be computed by sorting on
   `appVersion`, **not** by walking chart versions, because of the six
   non-monotonic steps.

Then override `image.tag` with the requested `--version` and `mongodb.image.tag`
with `versions.resolve().mongo_tag` regardless of which chart was selected. The
chart version chosen is only the *template* version; the running Rocket.Chat and
MongoDB versions come from rc-repro.

Why not the alternatives:

- **Static table only.** Rejected. 95 chart releases and growing; a shipped
  table goes stale on every chart release, and unlike MongoDB pairings (which
  are stable per Rocket.Chat major) chart releases land monthly to weekly
  (verified from the GitHub releases dates: three `rocketchat-*` releases
  between 2026-06-15 and 2026-07-30). It would also duplicate data that is
  already served as a machine-readable index.
- **Live query only.** Rejected. rc-repro supports an offline/airgapped path
  (`versions.resolve(offline=True)` at `versions.py:119`,
  `rc_repro/data/presets/airgapped.yaml`), and the map requires the preset to
  work through the normal lifecycle. A resolver with no fallback breaks offline
  use. A minimal floor table (one entry per Rocket.Chat major, mirroring the
  shape of `data/versions.yaml:18-42`) is enough, because `image.tag` carries
  the real version anyway, so an approximate chart choice degrades gracefully.
- **Shelling out to `helm search repo rocketchat/rocketchat --versions`.**
  Rejected as the resolution mechanism. It requires a Helm binary plus a
  `helm repo add`/`helm repo update` side effect on the user's Helm config
  before rc-repro can even answer a version question, and it writes to shared
  user state. Reading `index.yaml` over HTTPS is side-effect free. Helm is still
  needed to *install*, just not to *resolve*.

Caching note: `index.yaml` at 118845 bytes is small enough to fetch per
invocation, and `versions.py` already uses `@lru_cache` (`versions.py:39`) for
the equivalent concern.

## 6. Verification

`helm version --short` -> `v4.2.3+g43e8b7f`. Rendered the downloaded
`rocketchat-7.0.2.tgz` with the recommended values shape:

```yaml
host: rc.localtest.me
image:
  tag: "8.2.0"          # <- rc-repro's --version
microservices:
  enabled: true
mongodb:
  enabled: true
  image:
    repository: bitnamilegacy/mongodb
    tag: "8.0"          # <- versions.resolve().mongo_tag
  auth: { rootPassword: rootpass, passwords: [rcpass], usernames: [rocketchat], databases: [rocketchat] }
```

`helm template` exited 0 with no stderr and produced 1695 lines. Distinct
container images in the output:

```
registry.rocket.chat/rocketchat/rocket.chat:8.2.0
rocketchat/account-service:8.2.0
rocketchat/authorization-service:8.2.0
rocketchat/ddp-streamer-service:8.2.0
rocketchat/presence-service:8.2.0
docker.io/bitnamilegacy/mongodb:8.0
docker.io/bitnamilegacy/mongodb-exporter:0.39.0-debian-11-r106
docker.io/bitnamilegacy/os-shell:11-debian-11-r72
nats:2.12-alpine
natsio/nats-box:0.19.2
natsio/nats-server-config-reloader:0.21.1
natsio/prometheus-nats-exporter:0.18.0
synadia/nats-box
```

Workloads rendered: Deployments `rc-rocketchat`, `rc-presence`,
`rc-ddp-streamer`, `rc-account`, `rc-authorization`, `rc-nats-box`;
StatefulSets `rc-mongodb`, `rc-nats`; plus Services, Secrets, ConfigMaps and a
NATS PodDisruptionBudget. No `stream-hub` Deployment, which is correct for
Rocket.Chat 8.2.0.

This is rendering only. Nothing was applied to any cluster.

## 7. Compatibility gaps and risks

1. **Stale default MongoDB (highest impact).** Chart default is MongoDB `6.0.x`
   against a Rocket.Chat 8.x appVersion. Forgetting `mongodb.image.tag` yields a
   deployment that is out of the documented compatibility envelope.
   **Verified fact.**
2. **The bundled MongoDB is being removed (announced).** The `helm-charts`
   repository README leads with an "Important Note!" telling users to move off
   the built-in Mongo, links
   `https://forums.rocket.chat/t/action-required-helm-chart-moving-from-bitnami-to-official-mongodb-chart/22679`,
   and states: "We will be removing the built in mongo using Bitnami in
   susequent versions." (`README.md:5-11` of `RocketChat/helm-charts`, fetched
   via `gh api`). Meanwhile `Chart.yaml:4-11` still resolves MongoDB and
   PostgreSQL from `https://charts.bitnami.com/bitnami`, and the chart already
   redirects the images to `bitnamilegacy/*` (the same relocation rc-repro
   documents at `data/versions.yaml:8-11`). **Verified fact.** Risk: a future
   chart release drops `mongodb.enabled` and the `mongodb.image.tag` override
   key disappears, forcing rc-repro onto `externalMongodbUrl`
   (`values.yaml:127`) plus its own MongoDB. Mitigation: assert on the rendered
   MongoDB image rather than on the values key, and treat
   `externalMongodbUrl` as the likely long-term seam. The forum post itself was
   not read; **inference** on the timing and the eventual shape.
3. **`microservices.enabled` default flipped** between chart `6.25.3` and
   `6.28.0`. Always set it explicitly. **Verified fact.**
4. **Stale chart README.** Documents `microservices.enabled: false` and
   `image.tag: 3.18.3`. Do not build the preset from the README.
   **Verified fact.**
5. **`image.tag` must be valid semver.** `_helpers.tpl:226` runs
   `semverCompare` on it. A non-semver tag will break Stream Hub gating and
   possibly other conditionals. **Verified fact.**
6. **No declared Kubernetes version floor.** `Chart.yaml` has no `kubeVersion`
   in `6.32.1` or `7.0.2`, and `index.yaml` reports `kubeVersion: None` for
   every entry. The only Kubernetes-version-sensitive template logic is
   `deployment.apiVersion` in `_helpers.tpl:71-76`, which emits
   `extensions/v1beta1` below 1.14 and `apps/v1` at 1.14 and above. So the chart
   declares no minimum: the local-cluster runtime choice is unconstrained by the
   chart, and also unvalidated by it. **Verified fact.**
7. **Premium license gate on microservices.** Helm will not stop a license-less
   install; the gate is at runtime. A Microservices Preset without a license may
   produce a workspace where the microservices are present but not functioning
   as licensed. **Verified** that the chart declares EE-only and does not
   validate; **inference** on runtime behaviour.
8. **BREAKING securityContext UID change.** Chart `7.0.0` release notes include
   "Update securityContext UID to 65533", and `values.yaml:108` reads
   "BREAKING CHANGE: UID changed from 999 to 65533". Straddling chart `6.32.x`
   and `7.0.x` with the same PersistentVolume will hit permission failures.
   **Verified fact.**
9. **Untagged `synadia/nats-box`** appears in the rendered NATS Helm test Pod,
   which resolves to `:latest` and is not reproducible. Low impact (it is a test
   hook, not a workload), but it means a fully version-pinned render is not
   achievable from chart defaults alone. **Verified fact.**
10. **Sparse chart coverage.** Most Rocket.Chat versions have no chart with a
    matching appVersion. This is fine given the `image.tag` override, but it
    means the resolver must never hard-fail on "no chart for this version".
    **Verified fact.**
11. **`index.yaml` `created` is not a release date.** Any resolver ordering by
    `created` will behave randomly. **Verified fact.**
12. **Resource footprint.** The microservices topology renders 6 Deployments and
    2 StatefulSets. Whether that fits a laptop-scale local cluster is exactly
    what the map lists as not yet specified. Not measured here.

## 8. What I could not determine

- Whether the official chart is also published to an OCI registry (for example
  `oci://registry.rocket.chat/...`). Only the HTTPS repo at
  `rocketchat.github.io/helm-charts` was verified.
- Any documented minimum Kubernetes version for the chart. None is declared in
  `Chart.yaml` and I did not find one in the docs.
- Whether the microservice Deployments need `ROCKETCHAT_LICENSE` themselves. The
  chart injects it only on the monolith Deployment; I could not verify what the
  microservices do without it.
- Actual runtime behaviour of a license-less microservices install. Not
  exercised against a cluster; only `helm template` was run.
- Whether Rocket.Chat publishes an authoritative Rocket.Chat-version-to-chart-version
  mapping anywhere. I found none.
- The target chart version or timeline for removing the bundled Bitnami MongoDB.
  The README announces it without a version; I did not read the linked forum
  post.
- The license of `RocketChat/helm-charts`. The GitHub API returns `null`.
- Whether `helm install --version <chart>` with a much newer `image.tag` than
  the chart's `appVersion` is supported by Rocket.Chat, or merely happens to
  render. Skew is bounded by the floor strategy but the supported skew window is
  undocumented.
- Whether `rocketchat-voip` or the `monitoring` chart are needed for the
  Microservices Preset's evidence and monitoring add-ons.

## 9. Where this touches rc-repro today

For the implementation ticket that follows. rc-repro has **no** Helm or
Kubernetes code at all right now: `grep -rl "helm\|kubectl\|kubernetes" rc_repro/`
returns nothing. **Verified fact.**

- `rc_repro/versions.py:119-148` (`resolve`) already returns everything the
  chart override needs: `rc_version` -> `image.tag`, `mongo_tag` ->
  `mongodb.image.tag`, `rc_image` -> `image.repository`. It should be reused
  unchanged, with chart resolution added alongside it rather than inside it.
- `rc_repro/versions.py:24` (`RELEASES_URL`) matches what Rocket.Chat's docs
  document as the authoritative source for `compatibleMongoVersions`
  ([supported-mongodb-versions](https://docs.rocket.chat/docs/supported-mongodb-versions),
  which shows `curl https://releases.rocket.chat/<VERSION>/info` and RC 8.2.0 ->
  `["8.0"]`, matching `data/versions.yaml:19-21`). **Verified fact.** No change
  needed.
- `rc_repro/versions.py:62-66` (`_flavor`) and `rc_repro/compose.py:111`
  already encode the `bitnamilegacy` decision that the chart also made. The
  Kubernetes path can reuse the same rule.
- `rc_repro/compose.py:18-59` (`Spec`) is Compose-shaped (`host_port`,
  `bind_host`, `container_port`). A Helm values builder is the parallel of
  `compose.build` (`compose.py:242`), not an extension of it.
- `rc_repro/presets/__init__.py:19-60` (`Preset`) is Compose-specific in its
  fields (`services`, `depends_on`, `volumes`, `entry_service`). The
  Microservices Preset needs `requires_license=True` and a values-shaped
  payload, which the current dataclass has no field for. That is the
  backward-compatibility seam the map flags as not yet specified.
- `rc_repro/presets/multi_instance.py:29` hand-pins `nats:2.11-alpine`; the
  chart pins `nats:2.12-alpine` and owns it. The Kubernetes path should not
  reuse rc-repro's NATS pin.

## Sources

- [Rocket.Chat docs: Deploy with Kubernetes](https://docs.rocket.chat/docs/deploy-with-kubernetes)
- [Rocket.Chat docs: Scaling Rocket.Chat with Microservices](https://docs.rocket.chat/docs/microservices)
- [Rocket.Chat docs: Check Your Supported Node.js and MongoDB Versions](https://docs.rocket.chat/docs/supported-mongodb-versions)
- [RocketChat/helm-charts](https://github.com/RocketChat/helm-charts) and its `README.md` (fetched via `gh api repos/RocketChat/helm-charts/contents/README.md`)
- Chart-internal docs read from the package: `rocketchat/README.md`, `rocketchat/values.yaml`, `rocketchat/Chart.yaml`, `rocketchat/Chart.lock`, `rocketchat/templates/_helpers.tpl`, `rocketchat/templates/_validations.yaml`, `rocketchat/templates/chat-deployment.yaml`, `rocketchat/templates/microservices-presence-deployment.yaml`, `rocketchat/templates/secret.yaml`, `rocketchat/tests/microservices-values.yaml`, `rocketchat/charts/mongodb/Chart.yaml`
- Chart index: `https://rocketchat.github.io/helm-charts/index.yaml` (generated 2026-07-30T12:22:36Z)
- Chart packages inspected: `rocketchat-7.0.2.tgz`, `rocketchat-6.32.1.tgz`, `rocketchat-6.28.0.tgz`, `rocketchat-6.25.3.tgz`, `rocketchat-6.20.0.tgz`, `rocketchat-6.5.3.tgz` from `https://rocketchat.github.io/helm-charts/charts/`
- `gh api repos/RocketChat/helm-charts`, `gh api repos/RocketChat/helm-charts/releases`
- Docker Hub tag API: `https://hub.docker.com/v2/repositories/rocketchat/<service>/tags/<tag>`
- rc-repro source in this worktree: `rc_repro/versions.py`, `rc_repro/data/versions.yaml`, `rc_repro/compose.py`, `rc_repro/presets/__init__.py`, `rc_repro/presets/multi_instance.py`
