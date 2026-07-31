# rc-repro-owned local Kubernetes runtime and resource contract

Design for the local cluster the `microservices` preset creates by default.
Resolves [Canepro/rc-repro#4](https://github.com/Canepro/rc-repro/issues/4). Planning
only: nothing here is implemented yet. rc-repro has no Kubernetes or Helm code today.

## Decisions

| # | Decision | Rejected alternative |
|---|---|---|
| D1 | **kind**, running on the container engine rc-repro already requires, auto-detecting Docker or Podman | minikube in its own VM; k3d; rc-repro managing a dedicated engine machine |
| D2 | Capacity acquired under **one-time onboarding consent**, then applied silently on later runs | hard-fail preflight every time; per-run authority gate; shrinking the topology to fit |
| D3 | **One rc-repro-owned cluster, one namespace per repro** | one kind cluster per repro |
| D4 | Ownership is **label-asserted**, and rc-repro deletes only what it owns | name-prefix matching; trusting the current context |

## D1: kind on the existing engine

kind runs the cluster as containers inside the engine rc-repro already requires, so there
is one engine to detect, one to preflight, and one failure surface. Verified properties
that matter here:

- kind supports Podman as a provider from kind 0.11.0 with Podman 3.0 or later, and
  auto-detects docker, podman, or nerdctl. Selection can be forced with
  `KIND_EXPERIMENTAL_PROVIDER=podman`
  ([kind rootless docs](https://kind.sigs.k8s.io/docs/user/rootless/),
  [quick start](https://kind.sigs.k8s.io/docs/user/quick-start/)).
- Deleting a cluster that does not exist is not an error, by design, as an idempotent way
  to clean up. That is a direct gift to the cleanup contract below: teardown never needs a
  pre-existence check ([quick start](https://kind.sigs.k8s.io/docs/user/quick-start/)).

### Why not the alternatives

**k3d** was rejected on documented evidence, not preference. Its own docs state Podman
support is experimental and that "k3d is not guaranteed to work with Podman", and the macOS
path additionally requires cpuset cgroup delegation, a
`KubeletInUserNamespace` kubelet feature gate, manual network creation because the default
Podman network has DNS disabled, and forbids `--registry-create`
([k3d Podman docs](https://k3d.io/stable/usage/advanced/podman/)). For a tool whose point is
removing red herrings from reproductions, that is a poor foundation.

**minikube with its own VM** was the strongest alternative, because sizing its own VM would
have made the capacity problem rc-repro's to solve rather than the user's. It was rejected
for adding a second VM competing for host RAM, a per-platform driver matrix (vfkit requires
macOS 14 or later and minikube 1.36 or later,
[vfkit driver](https://minikube.sigs.k8s.io/docs/drivers/vfkit/)), and for splitting
rc-repro's Kubernetes path off the engine its Docker path already uses.

### Host platform support

| Platform | Engine | Support intent |
|---|---|---|
| macOS, Apple Silicon | Podman machine or Docker Desktop | primary, this is the development host |
| macOS, Intel | Podman machine or Docker Desktop | same code path, untested |
| Linux, rootful Docker | Docker | expected to be the simplest case |
| Linux, rootless Podman | Podman | supported with caveats, see below |
| Windows | Docker Desktop or Podman via WSL2 | not targeted in the first change |

Rootless Podman carries kind's documented caveats: OverlayFS, block storage, and NFS
restrictions apply, and rootless Podman's log handling can make kind report failure even
when the cluster started, with the documented workaround being the `k8s-file` log driver
([kind rootless docs](https://kind.sigs.k8s.io/docs/user/rootless/)). Preflight should detect
rootless Podman and check the log driver, because that is precisely the class of misleading
failure rc-repro exists to eliminate.

### Reproducibility

The Kubernetes version must be deterministic, so rc-repro pins the kind node image by tag
and digest (`kindest/node:vX.Y.Z@sha256:...`) rather than accepting kind's default, and
records the pinned image plus the kind version in the evidence record. The research on
ticket #2 found no documented minimum Kubernetes version for the official chart, so the pin
is rc-repro's choice of a known-good version, not a constraint read off the chart.

rc-repro reads the kubectl context name from kind's own output rather than assuming kind's
naming convention, and then passes that context explicitly on every command. This is the
enforcement point for the map's rule that the ambient `kubectl` context is never selected
implicitly.

## D2: capacity under one-time consent

The problem is concrete on the development host: 16 GiB of RAM and 10 CPUs, but
`podman-machine-default` is allocated 5 CPUs and 2 GiB. Because kind runs inside that
engine, the cluster inherits the 2 GiB ceiling. Six Deployments and two StatefulSets
including MongoDB and NATS will not fit in 2 GiB.

The tension this decision resolves: the goal is autopilot with as little human authoring as
possible, but the only way to raise that ceiling is to stop, resize, and restart a VM the
user has other work in.

**The contract:**

1. Onboarding asks **once** whether rc-repro may stop, resize, and restart the container
   engine VM when a preset needs more capacity, and persists the answer. This is the map's
   existing rule that persisted preferences give standing authority within scope, not a new
   mechanism.
2. With consent persisted, later runs resize silently and never prompt. Preflight reports
   what it did as a `preflight` phase event, so the action is visible in the stream without
   being a question.
3. Without consent, preflight fails with exit 3 and a remedy naming the exact command, per
   the contract in #6. It does not re-ask, because re-asking a settled question is the thing
   onboarding exists to prevent.
4. Resizing is never silent about *scope*: the onboarding prompt must say plainly that
   restarting the engine stops unrelated containers, because that is the real cost.

**The accepted risk, stated plainly:** consent granted months earlier will one day stop the
engine while unrelated work is running, and rc-repro will be correctly inside its authority
when it does. Two mitigations that do not reintroduce a prompt: refuse to resize while
containers rc-repro does not own are running, and always report the resize as an event
rather than performing it silently.

**The floor itself is unmeasured.** The chart renders 6 Deployments and 2 StatefulSets, and
the research for #2 explicitly did not measure the footprint. Publishing a guessed floor
would be the sort of confident-but-wrong number that wastes a debugging afternoon, so the
number is deferred to a measurement task rather than invented here. The contract shape,
preflight enforces a published floor, is what this ticket settles.

## D3: one cluster, one namespace per repro

Settled on an existing invariant rather than preference: rc-repro already supports several
concurrent repros (`list`, `use`, `prune`, and a default-repro concept). A kind cluster per
repro means a control plane per repro, which on a 16 GiB host effectively forbids running
two at once. That would silently break behavior rc-repro already has.

- Cluster: one rc-repro-owned cluster, created on demand.
- Repro: one namespace per repro, so `up` creates a namespace and `down` deletes it.
- The cluster outlives individual repros. It is warm, which also makes the second `up`
  much faster than the first.
- `prune` deletes the cluster once no rc-repro namespaces remain, matching how `prune`
  already reclaims down repros.

**Objection:** a namespace is a weaker boundary than a cluster. Two repros share one
control plane, one set of nodes, and one Kubernetes version, so a repro cannot pin a
different Kubernetes version from its neighbour, and a workload that exhausts node memory
degrades every repro on the cluster. That is a real fidelity loss and is the price of
keeping concurrent repros working on laptop-scale hardware. If per-repro Kubernetes version
pinning is ever needed, it becomes a cluster-per-repro opt-in rather than the default.

## D4: ownership and cleanup

rc-repro must never delete something a human owns. That is a map-level gate, and on a
shared cluster it needs a mechanism rather than a convention.

Everything rc-repro creates carries:

```yaml
labels:
  app.kubernetes.io/managed-by: rc-repro
  rc-repro.io/repro: <name>
```

Rules:

- Teardown selects by label, never by name prefix. A namespace called `rc-repro-foo` that
  lacks the label is not rc-repro's and is left alone.
- Deleting the cluster requires that rc-repro created it, asserted by an annotation written
  at creation. An existing cluster that happens to share the name is never deleted.
- An opted-in existing cluster (the map allows this as an explicit persisted opt-in) is
  never deleted by rc-repro under any circumstance. Only namespaces rc-repro owns within it
  are removed.
- Teardown is idempotent, which kind already guarantees for cluster deletion and which
  namespace deletion gives for free.
- Deleting anything unlabelled is the `GATE_DELETE_UNOWNED` gate from #6, exit 6, never
  auto-approvable.

## What this does not decide

- The actual memory and CPU floor. Deferred to a measurement task, because it must be
  measured against the real chart rather than guessed.
- Which Kubernetes version to pin. It depends on measuring the chart against a few
  candidates, and no minimum is documented upstream.
- How Helm values are built and how the lifecycle wires in. That is
  [#5](https://github.com/Canepro/rc-repro/issues/5).
- Whether the premium licence gate on microservices makes a licence-less local repro
  useful at all. The #2 research verified the chart declares microservices as enterprise
  and does not validate a licence, but could not verify runtime behaviour without one. This
  is a real open risk to the whole preset and is recorded on the map rather than buried
  here.
