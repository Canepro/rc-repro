# How Kubernetes joins the rc-repro lifecycle

Design for integrating the `microservices` preset into rc-repro's existing lifecycle.
Resolves [Canepro/rc-repro#5](https://github.com/Canepro/rc-repro/issues/5). Planning only.

## Decisions

| # | Decision | Rejected alternative |
|---|---|---|
| D1 | **Parallel path**: a new `services/k8s.py` beside `services/lifecycle.py`, dispatched once per public entry point | a backend Protocol refactoring both; branching inside existing functions |
| D2 | **`kubectl port-forward` per repro**, keeping `host_port` and `root_url` semantics identical | NodePort with pre-declared mappings; in-cluster ingress |
| D3 | The port-forward is **reconcilable state**, re-established on demand rather than assumed alive | treat it as fire-and-forget; require a long-lived daemon |
| D4 | Compose-only flags **fail loudly** on a Kubernetes topology rather than being ignored | silently accept and no-op |

## Why a parallel path

`services/lifecycle.py` is 597 lines with **43 Docker and Compose references**, including
`compose_exec`, `compose_exec_capture`, `rm_services`, and `service_container_ids`. The web
GUI depends on the same module. A Protocol refactor is the cleaner long-term shape, and it was
rejected on contribution grounds rather than on architecture: it would rewrite working Docker
behaviour in a module two front-ends depend on, which is the hardest possible change to ask an
upstream maintainer to accept from an outside contributor. The parallel path is additive and
leaves the default path byte-identical.

The accepted cost is duplication of orchestration shape (readiness polling, metadata writing,
teardown sequencing) that can drift. The mitigation is an explicit list of what stays shared,
below, rather than a hope that it will.

### Dispatch

One branch per public entry point, delegating wholesale. Each branch is a single line, so this
is not the "scattered branching" the rejected third option would have produced:

```python
def create_repro(req: CreateReq, emit=null_emit, *, stream_output=False) -> dict:
    if presets.get(req.preset).topology == "kubernetes":
        return k8s.create_repro(req, emit, stream_output=stream_output)
    ...existing compose body, unchanged...
```

Dispatch lives in the **service layer**, not the CLI, because the web GUI calls the same
functions and must get the same behaviour.

Topology source of truth: a new `Preset.topology` field defaulting to `"compose"`, so every
existing preset keeps its behaviour without being touched. It is persisted into
`Metadata.extra["topology"]` at create time. `extra` already exists (`runner.py:50`) with a
default factory, so old `repro.json` records still read cleanly and no dataclass field is
added.

## Reachability

`kubectl port-forward` from a per-repro host port to the Rocket.Chat Service. This is the only
option that gives each repro its own port on the single warm cluster #4 chose, because kind
fixes `extraPortMappings` at cluster creation and the cluster outlives individual repros.

It also keeps `host_port` and `root_url` meaning exactly what they mean today, so
`wait_serving`, `seed`, `evidence`, `serve`, and browser checks need no Kubernetes awareness at
all. That is the single biggest reason the parallel path stays small.

### The port-forward is state, not an assumption

The honest weakness of port-forward is that it is a child process that dies with the CLI. Rather
than pretend otherwise, treat it as reconcilable:

- `up` starts the forward detached and records the pid and port in `Metadata.extra`.
- Any operation needing HTTP (`ready`, `seed`, `info`, `evidence`) **probes the forward first
  and re-establishes it if dead**. Re-establishing is idempotent and costs milliseconds.
- `down` terminates it before removing cluster resources.
- `info` reports `port_forward: up|down` as a distinct field. A repro whose forward died is
  still running in the cluster, and reporting it as broken would be wrong.

This is why D3 exists as a decision: without it, every verb inherits a flaky precondition.

## Lifecycle parity

| Verb | Compose path today | Kubernetes path |
|---|---|---|
| `up` | render `docker-compose.yml` into the workspace, `compose up` | ensure cluster, create labelled namespace, render `values.yaml` into the same workspace, `helm install` |
| `ready` | HTTP poll on `host_port` | **identical**, `wait_serving` reused unchanged through the forward |
| `list` | read `repro.json` records | **identical**, records are backend-agnostic |
| `info` | `compose ps` to `{service,state,status}` | `kubectl get pods` mapped to the **same** shape, plus `port_forward` |
| `logs` | `compose logs [-f] [--tail]` | `kubectl logs` with a deployment selector, `-f` to `--follow`, `--tail` passed through |
| `exec` | `compose exec <service>` | `kubectl exec` into the deployment's pod |
| `evidence` | `compose_sha256`, docker and compose versions | `values_sha256`, chart version, kind version, node image digest, Kubernetes version |
| `down` | `compose down`, `--volumes` removes volumes | kill forward, `helm uninstall`, delete namespace; `--volumes` also deletes PVCs |
| `prune` | delete down repros | same, and delete the cluster once no rc-repro-owned namespaces remain (per #4) |
| `restart` | `compose restart` | `kubectl rollout restart` on the namespace's deployments |
| `doctor` | engine, compose, disk, ports, kernel | same checks **plus** cluster reachability, an image-architecture check, and the measured floor |

The workspace directory keeps its role: it holds the rendered artifact (`values.yaml` instead of
`docker-compose.yml`) plus `repro.json`. Evidence hashes the rendered artifact either way, so
reproducibility works identically.

## What stays shared, explicitly

This list is the mitigation for the duplication cost. These are reused unchanged, not
reimplemented:

- `sanitize`, `derive_name`, `resolve_name` for naming.
- `pick_host_port` and the port-collision checks, still needed for the forward's host port.
- `runner.Metadata`, `runner.write`, `read_meta`, `workspace`.
- `versions.resolve`, unchanged. The #2 research confirmed it already returns everything the
  chart override needs: `rc_version` to `image.tag`, `mongo_tag` to `mongodb.image.tag`,
  `rc_image` to `image.repository`.
- `wait_serving`, because readiness is an HTTP fact, not a backend fact.
- The `Event` emitter and the closed phase vocabulary from #6, with Kubernetes emitting the
  `provision` phase that Compose does not.
- Evidence assembly and the `rc-repro.evidence.v2` envelope from #6.

Not shared, because they are genuinely Compose-specific: `own_ports` internals,
`check_sidecar_ports`, `compose_exec*`, `rm_services`, `service_container_ids`.

## MongoDB selection, grounded in measurement

The [#12 measurement](https://github.com/Canepro/rc-repro/issues/12) makes this concrete rather
than theoretical:

- **Never accept the chart's default MongoDB tag.** Chart 7.0.2 declares appVersion 8.6.1 and
  defaults MongoDB to 6.0.10, which Rocket.Chat 8.6.1 rejects with exit 1.
- **Default path (amd64, kernel below 6.19):** keep the chart's bundled MongoDB subchart and
  override `mongodb.image.tag` from `versions.resolve`. Verified working with 8.0.13.
- **Fallback path (arm64, or kernel 6.19 and above):** the bundled subchart cannot work, because
  Bitnami publishes no arm64 MongoDB image and official MongoDB 8.0 refuses to start on kernel
  6.19+. Set `mongodb.enabled=false` and point `externalMongodbUrl` at a MongoDB the preset
  manages, as a **single-node replica set**, which Rocket.Chat requires for change streams.
- Preflight, not runtime, chooses between these, using `doctor`'s existing kernel check
  (`cli.py:1645`) plus an image-architecture check.
- MongoDB majors cannot be upgraded in place, so the tag must be resolved before first install.

## Public CLI compatibility

No new required flags, and no changed meanings. `--preset microservices` selects the topology;
`--version`, `--rc-tag`, `--name`, `--port`, `--bind`, `--volumes`, `--wait`, `--timeout` all
keep their current semantics.

Compose-only options (monitoring sidecars, `--scale`, and anything reaching into a Compose
service by name) **fail loudly** on a Kubernetes topology with exit 2 and
`VALIDATION_FAILED` per the #6 contract, naming the flag and the topology. Silently accepting a
flag that does nothing is the failure mode that costs someone an afternoon, which is the thing
rc-repro exists to prevent.

## What this does not decide

- The terminal-versus-transient failure table, which is
  [#11](https://github.com/Canepro/rc-repro/issues/11).
- Monitoring, load testing, and other cross-cutting add-ons on Kubernetes, which remain map fog
  until a first lifecycle exists.
- Evidence retention and ownership beyond the ownership labels from #4, which is
  [#9](https://github.com/Canepro/rc-repro/issues/9).
- Whether an unlicensed microservices repro is useful at all, which is
  [#13](https://github.com/Canepro/rc-repro/issues/13).
