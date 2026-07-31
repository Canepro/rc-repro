# Microservices topology on a local kind cluster: first run findings

Evidence from actually standing the official chart's microservices topology up on a local
kind cluster, for [Canepro/rc-repro#12](https://github.com/Canepro/rc-repro/issues/12).

**Status: the footprint floor is NOT established by this run.** The host is not a
representative baseline. What this run did establish is a failure matrix that rc-repro's
preflight has to detect, which is arguably the more useful output.

## Host

| Piece | Value |
|---|---|
| Host | macOS, Apple Silicon, 16 GiB RAM, 10 CPUs |
| Engine | Podman 6.0.2, `podman-machine-default` resized 2 GiB to 6 GiB, 5 CPUs |
| VM kernel | `6.19.7-200.fc43.aarch64` |
| kind | v0.32.0, provider `podman` |
| Node image | `kindest/node:v1.36.1`, digest `sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5` |
| Cluster | `rc-repro-local`, context `kind-rc-repro-local` |
| helm | v4.2.3 |

Most rc-repro users are on Docker, not Podman, and on amd64, not arm64. Treat every number
below as arm64-and-Podman-specific.

## Verified findings

### 1. The chart's microservices default contradicts its own comment

`helm show values rocketchat/rocketchat --version 7.0.2` contains:

```yaml
## Deploy as microservices?
# Monolithic architecture, by default
microservices:
  enabled: true
```

The comment says monolith, the value says microservices. `helm template` with pure defaults
confirms the value wins: 6 Deployments (`rocketchat`, `account`, `authorization`,
`ddp-streamer`, `presence`, `nats-box`) and 2 StatefulSets (`mongodb`, `nats`), matching the
counts the #2 research predicted. **Installing this chart with defaults gets you
microservices, not a monolith.** Worth reporting upstream.

### 2. The chart declares no resource requests at all

Every microservice block is `resources: {}`. Nothing can be read off the chart about its
footprint, and Kubernetes cannot schedule on declared need. This confirms the premise of
#12: the floor has to be measured, and there was never a number to look up.

### 3. Chart 7.0.2 ships a MongoDB its own appVersion rejects

Chart 7.0.2 declares appVersion 8.6.1 and deploys
`docker.io/bitnamilegacy/mongodb:6.0.10-debian-11-r8`. Rocket.Chat 8.6.1 starts, detects
MongoDB 6.0.10, prints "PLEASE UPGRADE TO VERSION 8.0 OR LATER", and exits **code 1**,
landing in `CrashLoopBackOff`. The chart's default MongoDB is incompatible with the chart's
own default Rocket.Chat.

### 4. Bitnami MongoDB images are amd64-only

Docker Hub reports a single architecture, `amd64`, for every tag checked: `6.0.10-debian-11-r8`,
`8.0.12`, `8.0.13`, `8.0.13-debian-12-r0`. Overriding `mongodb.image.tag` to 8.0.13 on arm64
fails at pull time with `no match for platform in manifest: not found`. Official
`mongo:8.0` publishes `amd64` and `arm64`.

This independently vindicates rc-repro's existing rule at `rc_repro/versions.py:62-66`, that
MongoDB 8+ uses the official multi-arch image and only older tags use bitnami-legacy. The
chart cannot satisfy that rule, because its MongoDB is a Bitnami subchart.

### 5. MongoDB 8.0 will not start on kernel 6.19, MongoDB 7.0 will

Official `mongo:8.0` on this VM exits fatally:

```
MongoDB cannot start: Linux kernel versions 6.19 and newer has a known incompatibility
with this version of MongoDB. See https://jira.mongodb.org/browse/SERVER-121912
```

Switching the same StatefulSet to `mongo:7.0` came up `1/1 Running` in 15 seconds. So the
guard is specific to MongoDB 8.x, not to MongoDB generally.

rc-repro's `doctor` **already warns about exactly this** (`rc_repro/cli.py:1645`). The
Kubernetes preflight must reuse that check rather than reimplement it.

### 6. The compounding consequence on this host

Three constraints intersect:

- Rocket.Chat 8.2+ requires MongoDB 8.0 (`rc_repro/data/versions.yaml:19-21`).
- MongoDB 8.0 cannot start on kernel 6.19+.
- The chart's bundled MongoDB has no arm64 build.

Therefore **Rocket.Chat 8.2 and newer cannot run microservices on this host at all**, by any
configuration. The newest viable line is Rocket.Chat 7.x with MongoDB 7.0.

### 7. The configuration that did work

Chart 6.27.1 (appVersion 7.11.0), the chart's MongoDB disabled, pointed at an official
MongoDB 7.0 single-node replica set:

```yaml
microservices:
  enabled: true
mongodb:
  enabled: false
externalMongodbUrl: "mongodb://mongo-0.mongo:27017/rocketchat?replicaSet=rs0"
externalMongodbOplogUrl: "mongodb://mongo-0.mongo:27017/local?replicaSet=rs0"
```

A single-node replica set is required, not a standalone mongod: Rocket.Chat needs change
streams. Rocket.Chat 7.x also still wants the oplog URL, matching rc-repro's own rule that
oplog applies below RC 8 (`rc_repro/data/versions.yaml:12`).

Result after roughly 3 to 4 minutes: 8 of 10 pods fully ready, `account`, `authorization`,
`presence`, `stream-hub`, both NATS pods, `nats-box`, and MongoDB all `Running`, with
`rocketchat` and `ddp-streamer` still converging.

### 8. Provisional footprint, not a floor

At 10 pods with Rocket.Chat still becoming ready:

| Measure | Value |
|---|---|
| kind node container memory | 3.19 GB of 6.18 GB (51.6%) |
| node cgroup total (includes page cache) | 4.06 GiB |
| kind node container CPU | 86.8% of 5 CPUs |

**CPU, not memory, looked like the binding constraint.** A floor recommendation that only
specifies memory would miss the thing that was actually saturated. Do not quote these as the
floor: Rocket.Chat had not finished starting, and the host is arm64 under Podman.

### 9. MongoDB majors cannot be upgraded in place

Pointing the StatefulSet at 8.0.13 over an existing 6.0.10 data directory left the mongodb
container unready. The tag has to be correct at create time, which means version resolution
must run before the first install, not as a later reconcile.

### 10. Restart exit codes usefully separate transient from terminal

Directly relevant to [#11](https://github.com/Canepro/rc-repro/issues/11):

| Observed | Exit | Classification |
|---|---|---|
| Rocket.Chat rejecting the MongoDB version | 1 | **terminal**, restarting will never fix it |
| `ddp-streamer` killed while dependencies were unready | 143 (SIGTERM) | **transient**, it recovered |
| Image pull with no matching platform | n/a, `ImagePullBackOff` | **terminal** |

A naive "CrashLoopBackOff means dead" rule would have aborted a run that recovered. Exit code
plus the pull-failure reason discriminates better than restart count alone.

## What kind itself did well

Cluster creation took **20 seconds** on Podman. No rootless log-driver problem occurred, so
the caveat kind documents did not bite here. `kind delete` behaved idempotently as
documented.

## Implications for the map

- **#5, lifecycle:** the preset should set `mongodb.enabled=false` and manage MongoDB itself
  against `externalMongodbUrl`, rather than use the chart's Bitnami subchart. That is the
  only way to honour rc-repro's existing flavor rule and the only way to work on arm64.
- **#4, runtime:** the Kubernetes preflight must reuse `doctor`'s existing kernel check
  (`cli.py:1645`), and should add an image-architecture check, since a wrong-arch pull is a
  terminal failure that looks like a network problem.
- **#12, floor:** still open. It needs a representative Docker on Linux amd64 host. This run
  should be treated as the failure matrix, not the measurement.
- **#13, licence:** not answered here. Rocket.Chat never reached a ready state long enough to
  test whether microservices function under a Cloud-registered licence.
