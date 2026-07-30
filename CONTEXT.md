# rc-repro

rc-repro creates disposable, version-matched Rocket.Chat environments for
reproducing product behaviour and collecting evidence.

## Language

**Reproduction Scenario**:
A named Rocket.Chat behaviour or integration context to reproduce, such as LDAP,
SAML, email, or object storage.
_Avoid_: Workload scenario, topology

**Workload Scenario**:
A named pattern of test traffic applied to a running reproduction, such as
messages, login, or a full user journey.
_Avoid_: Reproduction scenario, preset

**Preset**:
A named catalog entry that configures a reproduction. A preset may describe an
integration scenario, a deployment topology, or both.
_Avoid_: Workload scenario

**Deployment Topology**:
The arrangement of Rocket.Chat instances and supporting components in a
reproduction, such as single-instance, Compose multi-instance, or Kubernetes
microservices.
_Avoid_: Scenario, execution target

**Microservices Preset**:
The built-in Kubernetes deployment preset for a Rocket.Chat microservices
reproduction, with the same create, readiness, inspection, evidence, and
teardown lifecycle as other rc-repro deployments. Docker remains rc-repro's
default deployment path.
_Avoid_: Kubernetes framework, topology catalog

**Execution Target**:
The runtime environment on which a reproduction is created, such as local
Docker, a remote container host, or a Kubernetes cluster.
_Avoid_: Topology, scenario

**Kubernetes Target**:
The explicitly selected cluster used by the Microservices Preset. It defaults
to an rc-repro-owned local cluster; an existing named cluster is opt-in, and
the ambient Kubernetes context is never selected implicitly.
_Avoid_: Current context, default cluster

**rc-repro Agent Skill**:
The standalone, portable rc-repro capability that onboards both a user and
their agent, persists agreed preferences, and lets the agent autonomously
operate rc-repro reproductions safely. Each run silently revalidates the current
environment without asking again unless a conflict requires a new human
decision or authority.
_Avoid_: Mira Workbench

**Mira Workbench**:
Vincent's personal general-purpose agent workbench for reproduction and
experimentation. It includes rc-repro as one first-class integration for easy
Rocket.Chat deployment lifecycles, but it is neither an rc-repro dependency nor
the upstream rc-repro skill.
_Avoid_: rc-repro wrapper, rc-repro Agent Skill
