"""Kubernetes topology: the `microservices` preset's create/ready/teardown.

A parallel path to services/lifecycle.py rather than a refactor of it. lifecycle.py
is Compose-shaped throughout and two front-ends depend on it, so the Docker default
stays byte-identical and this module owns the Kubernetes lifecycle instead. Naming,
version resolution, metadata, and readiness are shared, not reimplemented.

Design notes worth knowing before changing anything here:

* **MongoDB is always external, never the chart's bundled subchart.** The chart
  ships Bitnami MongoDB, and Bitnami publishes amd64-only images, so the bundled
  path cannot work on arm64 at all. Its default tag is also wrong: chart 7.0.2
  declares appVersion 8.6.1 and defaults MongoDB to 6.0.10, which Rocket.Chat
  8.6.1 rejects outright. One external path that works everywhere beats two paths
  where one is broken on half the hosts.
* **MongoDB runs as a single-node replica set**, not a standalone mongod, because
  Rocket.Chat needs change streams.
* **MongoDB 8.0 cannot start on Linux kernel 6.19 or newer** (SERVER-121912). With
  Rocket.Chat 8.2+ requiring MongoDB 8.0, that combination is impossible rather
  than slow, so preflight refuses it instead of timing out.

All external commands go through `_Runner`, so tests drive this module without a
cluster.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import yaml
from dataclasses import dataclass, field

from rc_repro import versions
from rc_repro.errors import DockerError, ValidationError
from rc_repro.services import events
from rc_repro.services.events import Emit, null_emit

#: The official chart. Never vendored: the chart is the topology's source of truth.
HELM_REPO_NAME = "rocketchat"
HELM_REPO_URL = "https://rocketchat.github.io/helm-charts"
CHART = "rocketchat/rocketchat"

#: The rc-repro-owned cluster. One cluster, a namespace per repro: a control plane
#: per repro would forbid concurrent repros on laptop-scale hardware, which is
#: behaviour rc-repro already has.
CLUSTER_NAME = "rc-repro-local"

#: Ownership labels. Teardown selects by these, never by name prefix, so a
#: namespace that merely looks like rc-repro's is left alone.
OWNER_LABEL = "app.kubernetes.io/managed-by=rc-repro"
REPRO_LABEL = "rc-repro.io/repro"

#: Measured floor for the microservices topology (see the #12 findings): peak
#: working set 3.49 GiB and ~3.5 of 4 cores during convergence. CPU is the binding
#: constraint, so a memory-only floor would miss it.
FLOOR_MEMORY_GIB = 6.0
FLOOR_CPUS = 4

#: MongoDB majors that cannot start on a 6.19+ kernel.
_KERNEL_BROKEN_MONGO_MAJOR = 8
_KERNEL_FIRST_BROKEN = (6, 19)


@dataclass
class _Runner:
    """Injectable command seam, so the whole module is testable offline."""

    def which(self, tool: str) -> str | None:
        return shutil.which(tool)

    def run(self, argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(argv, capture_output=True, text=True, check=check)

    def apply(self, ctx: str, ns: str, manifest: str) -> subprocess.CompletedProcess:
        """kubectl apply from stdin. Part of the seam so tests can capture it."""
        return subprocess.run(
            ["kubectl", "--context", ctx, "-n", ns, "apply", "-f", "-"],
            input=manifest, capture_output=True, text=True, check=True)

    def install(self, ctx: str, ns: str, values: dict) -> subprocess.CompletedProcess:
        """helm install with values on stdin, so no temp file is left behind."""
        return subprocess.run(
            ["helm", "install", "rc", CHART, "--kube-context", ctx,
             "-n", ns, "--values", "-"],
            input=yaml.safe_dump(values), capture_output=True, text=True, check=True)


@dataclass
class Plan:
    """Everything resolved before anything is created, so a dry run is possible."""
    name: str
    namespace: str
    rc_version: str
    rc_image: str
    mongo_tag: str
    chart_version: str = ""
    values: dict = field(default_factory=dict)


def namespace_for(name: str) -> str:
    return f"rc-repro-{name}"


def require_tools(run: _Runner | None = None) -> None:
    """kind, kubectl, and helm must all be present before anything is attempted."""
    run = run or _Runner()
    missing = [t for t in ("kind", "kubectl", "helm") if not run.which(t)]
    if missing:
        raise DockerError(
            "the microservices preset needs " + ", ".join(missing) +
            " on PATH (kind provisions the cluster, helm installs the chart)")


def _kernel_version(run: _Runner) -> tuple[int, int] | None:
    """The engine VM's kernel, which is what MongoDB actually runs on.

    On macOS the host kernel is irrelevant: containers run in the Podman/Docker
    VM, so the VM's kernel is the one SERVER-121912 applies to.
    """
    try:
        res = run.run(["docker", "info", "--format", "{{.KernelVersion}}"], check=False)
    except OSError:
        return None
    m = re.match(r"(\d+)\.(\d+)", (res.stdout or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def check_mongo_kernel_support(mongo_tag: str, run: _Runner | None = None) -> None:
    """Refuse the impossible combination rather than letting it time out.

    MongoDB 8.0 hard-exits on kernel 6.19+, and Rocket.Chat 8.2+ requires MongoDB
    8.0, so on such a host that Rocket.Chat line simply cannot run. Saying so up
    front is the whole point of preflight.
    """
    run = run or _Runner()
    try:
        major = int(str(mongo_tag).split(".")[0])
    except ValueError:
        return
    if major < _KERNEL_BROKEN_MONGO_MAJOR:
        return
    kernel = _kernel_version(run)
    if kernel and kernel >= _KERNEL_FIRST_BROKEN:
        raise ValidationError(
            f"MongoDB {mongo_tag} cannot start on engine kernel "
            f"{kernel[0]}.{kernel[1]} (SERVER-121912), and this Rocket.Chat "
            f"version requires it. Use an older Rocket.Chat line (7.x pairs with "
            f"MongoDB 7.0) or an engine on a kernel below 6.19.")


def build_values(rc_version: str, *, offline: bool = False,
                 rc_image: str = "", mongo: str = "") -> Plan:
    """Resolve versions and render the Helm values for one repro.

    Reuses versions.resolve unchanged: it already returns everything the chart
    override needs (rc_version -> image.tag, rc_image -> image.repository,
    mongo_tag -> the external MongoDB tag).
    """
    r = versions.resolve(rc_version, offline=offline)
    tag = mongo or r.mongo_tag
    values = {
        "image": {"repository": rc_image or r.rc_image, "tag": rc_version},
        "microservices": {"enabled": True},
        # Never the bundled subchart: Bitnami is amd64-only and the chart's
        # default MongoDB tag is rejected by its own appVersion.
        "mongodb": {"enabled": False},
        "externalMongodbUrl":
            "mongodb://mongo-0.mongo:27017/rocketchat?replicaSet=rs0",
    }
    if r.oplog:
        # Rocket.Chat below 8.x still wants the oplog URL; 8.x deprecates it.
        values["externalMongodbOplogUrl"] = \
            "mongodb://mongo-0.mongo:27017/local?replicaSet=rs0"
    return Plan(name="", namespace="", rc_version=rc_version,
                rc_image=rc_image or r.rc_image, mongo_tag=tag, values=values)


def cluster_exists(run: _Runner | None = None) -> bool:
    run = run or _Runner()
    res = run.run(["kind", "get", "clusters"], check=False)
    return CLUSTER_NAME in (res.stdout or "").split()


def ensure_cluster(emit: Emit = null_emit, run: _Runner | None = None) -> str:
    """Create the rc-repro-owned cluster if it isn't there, and return its context.

    The context name is read from kubectl rather than assumed from kind's naming
    convention, and then passed explicitly on every call. That is the enforcement
    point for never selecting the ambient kubectl context implicitly.
    """
    run = run or _Runner()
    if cluster_exists(run):
        events.info(emit, f"reusing cluster {CLUSTER_NAME}", phase="provision")
    else:
        events.info(emit, f"creating cluster {CLUSTER_NAME}", phase="provision", pct=10)
        run.run(["kind", "create", "cluster", "--name", CLUSTER_NAME])
    res = run.run(["kind", "get", "kubeconfig", "--name", CLUSTER_NAME], check=False)
    # kind names the context kind-<cluster>; confirm rather than assume, so a
    # future naming change surfaces here instead of silently targeting nothing.
    ctx = f"kind-{CLUSTER_NAME}"
    if res.stdout and f"name: {ctx}" not in res.stdout and "current-context:" in res.stdout:
        for line in res.stdout.splitlines():
            if line.startswith("current-context:"):
                ctx = line.split(":", 1)[1].strip()
                break
    return ctx


def _kubectl(run: _Runner, ctx: str, *args: str, check: bool = True):
    return run.run(["kubectl", "--context", ctx, *args], check=check)


def owns_namespace(ns: str, ctx: str, run: _Runner | None = None) -> bool:
    """Whether rc-repro created this namespace, asserted from its label.

    Name-prefix matching is not ownership: a namespace called rc-repro-foo without
    the label belongs to somebody else and must never be deleted.
    """
    run = run or _Runner()
    res = _kubectl(run, ctx, "get", "namespace", ns, "-o",
                   "jsonpath={.metadata.labels}", check=False)
    if res.returncode != 0:
        return False
    try:
        labels = json.loads(res.stdout or "{}")
    except ValueError:
        return False
    return labels.get("app.kubernetes.io/managed-by") == "rc-repro"


#: MongoDB as a single-node replica set. Not a standalone mongod: Rocket.Chat needs
#: change streams. The official image is used rather than Bitnami's because it is
#: the only one published for arm64.
_MONGO_MANIFEST = """\
apiVersion: v1
kind: Service
metadata:
  name: mongo
  labels: {{{owner}, {repro}: {name}}}
spec:
  clusterIP: None
  selector: {{app: mongo}}
  ports: [{{port: 27017, name: mongo}}]
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mongo
  labels: {{{owner}, {repro}: {name}}}
spec:
  serviceName: mongo
  replicas: 1
  selector: {{matchLabels: {{app: mongo}}}}
  template:
    metadata:
      labels: {{app: mongo, {owner}, {repro}: {name}}}
    spec:
      containers:
      - name: mongod
        image: mongo:{tag}
        args: ["--replSet", "rs0", "--bind_ip_all"]
        ports: [{{containerPort: 27017}}]
"""


def _mongo_manifest(name: str, tag: str) -> str:
    # The labels are inline YAML flow maps, so they need the key: value form the
    # label constants already carry as "k=v".
    owner_k, owner_v = OWNER_LABEL.split("=", 1)
    return _MONGO_MANIFEST.format(
        owner=f"{owner_k}: {owner_v}", repro=REPRO_LABEL, name=name, tag=tag)


def create_repro(name: str, rc_version: str, *, offline: bool = False,
                 rc_image: str = "", mongo: str = "", emit: Emit = null_emit,
                 run: _Runner | None = None) -> dict:
    """Create a Kubernetes microservices repro. Returns the result payload."""
    run = run or _Runner()
    require_tools(run)

    events.info(emit, "resolving versions and chart", phase="resolve", pct=5)
    plan = build_values(rc_version, offline=offline, rc_image=rc_image, mongo=mongo)
    plan.name, plan.namespace = name, namespace_for(name)
    # Fail on the impossible combination now rather than after a long wait.
    check_mongo_kernel_support(plan.mongo_tag, run)

    ctx = ensure_cluster(emit, run)

    events.info(emit, f"creating namespace {plan.namespace}", phase="provision", pct=20)
    _kubectl(run, ctx, "create", "namespace", plan.namespace, check=False)
    # Ownership is asserted at creation, so teardown can prove what it may delete.
    _kubectl(run, ctx, "label", "namespace", plan.namespace,
             OWNER_LABEL, f"{REPRO_LABEL}={name}", "--overwrite")

    events.info(emit, f"starting MongoDB {plan.mongo_tag}", phase="boot", pct=30)
    run.apply(ctx, plan.namespace, _mongo_manifest(name, plan.mongo_tag))
    events.info(emit, "waiting for MongoDB", phase="wait", pct=40)
    _kubectl(run, ctx, "-n", plan.namespace, "wait", "--for=condition=Ready",
             "pod/mongo-0", "--timeout=180s", check=False)
    # A single-node replica set must be initiated once; re-running rs.initiate on
    # an initiated set is an error, so failure here is expected on reuse.
    _kubectl(run, ctx, "-n", plan.namespace, "exec", "mongo-0", "--",
             "mongosh", "--quiet", "--eval",
             'rs.initiate({_id:"rs0",members:[{_id:0,host:"mongo-0.mongo:27017"}]})',
             check=False)

    events.info(emit, "installing the Rocket.Chat chart", phase="boot", pct=55)
    run.run(["helm", "repo", "add", HELM_REPO_NAME, HELM_REPO_URL], check=False)
    run.run(["helm", "repo", "update", HELM_REPO_NAME], check=False)
    run.install(ctx, plan.namespace, plan.values)

    events.info(emit, "chart installed", phase="wait", pct=70)
    return {"name": name, "namespace": plan.namespace, "context": ctx,
            "topology": "kubernetes", "rc_version": plan.rc_version,
            "mongo_tag": plan.mongo_tag, "chart": CHART}


def teardown(name: str, *, volumes: bool = False, emit: Emit = null_emit,
             run: _Runner | None = None) -> dict:
    """Remove a repro's namespace, reporting anything left behind.

    `residual` is the point: a partial teardown must not claim success. A tool that
    says "removed" while a volume survives is how a retained repro goes unnoticed
    for days.
    """
    run = run or _Runner()
    require_tools(run)
    ns = namespace_for(name)
    ctx = f"kind-{CLUSTER_NAME}"
    removed: list[str] = []
    residual: list[str] = []

    if not owns_namespace(ns, ctx, run):
        # Either it never existed (already gone, which is fine and idempotent) or
        # it is not ours, which is never ours to delete.
        return {"name": name, "removed": [], "residual": [], "volumes_removed": False}

    events.info(emit, f"deleting namespace {ns}", phase="teardown", pct=50)
    res = _kubectl(run, ctx, "delete", "namespace", ns, "--wait=true", check=False)
    if res.returncode == 0:
        removed.append(f"namespace/{ns}")
    else:
        residual.append(f"namespace/{ns}")

    if volumes:
        pv = _kubectl(run, ctx, "get", "pv", "-o",
                      "jsonpath={range .items[*]}{.metadata.name} ", check=False)
        for vol in (pv.stdout or "").split():
            if name in vol:
                residual.append(f"pv/{vol}")

    return {"name": name, "removed": removed, "residual": residual,
            "volumes_removed": bool(volumes)}
