"""On-disk repro state and docker-compose invocations.

Each repro is a workspace dir under ~/.rc-repro/repros/<name>/ holding the
generated docker-compose.yml and a repro.json metadata file.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from rc_repro import config


@dataclass
class Metadata:
    name: str
    project: str
    rc_version: str
    rc_image: str
    mongo_tag: str
    mongo_flavor: str
    preset: str
    root_url: str
    host_port: int
    version_source: str
    pinned: bool = False
    created_at: str = ""
    rc_tag: str = ""
    bind_host: str = config.DEFAULT_BIND_HOST
    extra: dict = field(default_factory=dict)


def project_name(name: str) -> str:
    return config.PROJECT_PREFIX + name


def workspace(name: str) -> Path:
    return config.repros_dir() / name


def exists(name: str) -> bool:
    return (workspace(name) / "docker-compose.yml").exists()


def write(name: str, compose_yaml: str, meta: Metadata,
          files: list[tuple[str, str]] | None = None) -> None:
    ws = workspace(name)
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "docker-compose.yml").write_text(compose_yaml, encoding="utf-8")
    (ws / "repro.json").write_text(json.dumps(asdict(meta), indent=2), encoding="utf-8")
    # Preset-generated files (e.g. a seeded LDIF that a service mounts).
    for relpath, content in files or []:
        fp = ws / relpath
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")


def read_meta(name: str) -> Metadata:
    blob = json.loads((workspace(name) / "repro.json").read_text(encoding="utf-8"))
    return Metadata(**blob)


def image_ref(meta: Metadata) -> str:
    return f"{meta.rc_image}:{meta.rc_tag or meta.rc_version}"


def _safe_root_origin(value: str) -> str:
    """Return only the HTTP(S) origin, excluding userinfo, path and query data."""
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except (UnicodeError, ValueError):
        return "REDACTED"
    if parsed.scheme not in {"http", "https"} or not hostname:
        return "REDACTED"
    if ":" in hostname:
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return f"{parsed.scheme}://{netloc}"


def evidence(name: str) -> dict:
    """Return a stable, secret-safe reproduction record."""
    meta = read_meta(name)
    compose_file = workspace(name) / "docker-compose.yml"
    digest = hashlib.sha256(compose_file.read_bytes()).hexdigest()
    docker_up = docker_available()
    services = []
    runtime_images = []
    state = "unknown"
    if docker_up:
        state = rc_state(name)
        for line in ps(name).splitlines():
            parts = line.split("\t", 2)
            services.append(
                {
                    "service": parts[0],
                    "state": parts[1] if len(parts) > 1 else "unknown",
                    "status": parts[2] if len(parts) > 2 else "",
                }
            )
        runtime_images = images(name)
    return {
        "schema": "rc-repro.evidence.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repro": {
            "name": meta.name,
            "project": meta.project,
            "rc_version": meta.rc_version,
            "image_ref": image_ref(meta),
            "mongo_tag": meta.mongo_tag,
            "mongo_flavor": meta.mongo_flavor,
            "preset": meta.preset,
            "root_url": _safe_root_origin(meta.root_url),
            "host_port": meta.host_port,
            "bind_address": meta.bind_host,
            "version_source": meta.version_source,
            "created_at": meta.created_at,
            "pinned": meta.pinned,
        },
        "runtime": {
            "state": state,
            "services": services,
            "images": runtime_images,
            "docker_available": docker_up,
            "docker_version": docker_server_version() if docker_up else None,
            "compose_version": compose_version() if docker_up else None,
        },
        "compose_sha256": digest,
    }


def list_meta() -> list[Metadata]:
    root = config.repros_dir()
    if not root.exists():
        return []
    out: list[Metadata] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        try:
            out.append(read_meta(d.name))
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            continue  # skip half-written / foreign dirs
    return out


def used_ports() -> set[int]:
    ports: set[int] = set()
    for m in list_meta():
        ports.add(m.host_port)
        # A multi-instance repro also occupies host_port+1..+N (direct instance
        # access), so those are claimed too.
        n = m.extra.get("instances") if isinstance(m.extra, dict) else None
        if isinstance(n, int) and n > 1:
            ports.update(m.host_port + i for i in range(1, n + 1))
        # Preset side services (Keycloak/Mailpit/MinIO…) publish fixed host
        # ports, recorded at `up` — claimed too, so allocation avoids them.
        side = m.extra.get("sidecar_ports") if isinstance(m.extra, dict) else None
        if isinstance(side, list):
            ports.update(int(p) for p in side if isinstance(p, int) or str(p).isdigit())
    return ports


PORT_MAX = 65535


def port_free(port: int) -> bool:
    """True if `port` can be bound on the host right now (nothing listening)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # On Unix, SO_REUSEADDR lets us probe a port that's only in TIME_WAIT.
        # On Windows it would let bind() succeed even for an active listener
        # (a false "free"), so skip it there.
        if sys.platform != "win32":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except (OSError, OverflowError):
            return False


def pick_port(start: int = 3000) -> int:
    """Lowest port >= start not claimed by another repro AND free on the host.

    Bounded: raises RuntimeError instead of scanning past 65535 (which happens
    when the host can't bind anything, e.g. sandboxed environments)."""
    used = used_ports()
    port = start
    while port in used or not port_free(port):
        port += 1
        if port > PORT_MAX:
            raise RuntimeError(
                f"no free host port found (scanned {start}-{PORT_MAX}) — "
                "can this environment bind TCP ports at all?"
            )
    return port


def pick_port_range(count: int, start: int = 3000) -> int:
    """Lowest base port with `count` consecutive ports all unclaimed AND free.

    Used by multi-instance repros, which need one port for the load balancer plus
    one per instance (the block [base, base+count)). Bounded like pick_port."""
    used = used_ports()
    base = start
    while not all((base + i) not in used and port_free(base + i) for i in range(count)):
        base += 1
        if base + count - 1 > PORT_MAX:
            raise RuntimeError(
                f"no free block of {count} consecutive host ports found "
                f"(scanned from {start}) — can this environment bind TCP ports at all?"
            )
    return base


def remove(name: str) -> None:
    shutil.rmtree(workspace(name), ignore_errors=True)


# --- docker compose -----------------------------------------------------------


def _compose(name: str, *args: str, capture: bool = False) -> subprocess.CompletedProcess:
    """Run `docker compose <args>` in a repro workspace."""
    cmd = ["docker", "compose", *args]
    return subprocess.run(
        cmd,
        cwd=workspace(name),
        text=True,
        capture_output=capture,
    )


def up(name: str, *, pull: bool = True) -> int:
    if pull:
        # A failed pull is deliberately non-fatal: cached images may satisfy
        # `up -d` anyway (e.g. registry hiccup), and `up` itself fails loudly
        # if an image is truly missing.
        _compose(name, "pull")
    # --remove-orphans: if the compose file changed shape (e.g. a different
    # preset after --force), containers of dropped services are cleaned up.
    return _compose(name, "up", "-d", "--remove-orphans").returncode


def down(name: str, *, volumes: bool = False) -> int:
    args = ["down", "--remove-orphans"]
    if volumes:
        args.append("-v")
    return _compose(name, *args).returncode


def start(name: str) -> int:
    return _compose(name, "start").returncode


def stop(name: str) -> int:
    return _compose(name, "stop").returncode


def restart(name: str) -> int:
    return _compose(name, "restart").returncode


def logs(name: str, *, follow: bool = False, tail: int | None = None) -> int:
    args = ["logs"]
    if follow:
        args.append("-f")
    if tail is not None:
        args += ["--tail", str(tail)]
    return _compose(name, *args).returncode


def compose_exec(name: str, service: str, args: list[str]) -> int:
    """Run a command inside a running compose service (docker compose exec -T)."""
    return _compose(name, "exec", "-T", service, *args).returncode


def ps(name: str) -> str:
    """Return `docker compose ps` for a repro (service/state/status lines)."""
    proc = _compose(
        name,
        "ps",
        "--all",
        "--format",
        "{{.Service}}\t{{.State}}\t{{.Status}}",
        capture=True,
    )
    return proc.stdout or ""


def images(name: str) -> list[dict[str, str]]:
    """Return safe image identity fields for a repro's created containers."""
    proc = _compose(name, "images", "--format", "json", capture=True)
    if proc.returncode != 0:
        return []
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        records = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        records = []
        for line in raw.splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    result = []
    for record in records:
        if not isinstance(record, dict):
            continue
        result.append(
            {
                "container": str(
                    record.get("Container")
                    or record.get("ContainerName")
                    or record.get("Service")
                    or ""
                ),
                "repository": str(record.get("Repository") or ""),
                "tag": str(record.get("Tag") or ""),
                "image_id": str(record.get("ID") or record.get("ImageID") or ""),
                "size": str(record.get("Size") or ""),
            }
        )
    return result


def rc_state(name: str) -> str:
    """Coarse state of the rocketchat service: running | exited | created | absent.

    One `docker compose ps` per call — fine for a single repro. For listing many
    repros use project_states() instead (a single docker call for all of them).
    """
    for line in ps(name).splitlines():
        parts = line.split("\t")
        # "rocketchat" for a normal repro, "rocketchat-1"/"-2"/… for a
        # multi-instance one — the first instance found is enough for readiness.
        if parts and (parts[0] == "rocketchat" or parts[0].startswith("rocketchat-")):
            return parts[1] if len(parts) > 1 else "unknown"
    return "absent"


def project_states() -> dict[str, str] | None:
    """Map compose project name -> status string for ALL projects, in one call.

    Uses `docker compose ls` so listing N repros costs one subprocess, not N.
    Status looks like "running(3)" / "exited(2)"; a fully `down`ed repro (no
    containers) is absent from the output. Returns None if the query itself
    failed — callers that DELETE based on absence (prune) must not confuse
    "no projects" with "couldn't ask docker".
    """
    proc = subprocess.run(
        ["docker", "compose", "ls", "--all", "--format", "json"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    raw = (proc.stdout or "").strip()
    if not raw:
        return {}
    # Newer compose emits a JSON array; older versions emit NDJSON (one object
    # per line). Handle both so `list` works across compose versions.
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            data = [data]
    except json.JSONDecodeError:
        data = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {item.get("Name", ""): item.get("Status", "") for item in data}


def docker_available() -> bool:
    try:
        proc = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
        return proc.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _first_line(cmd: list[str]) -> str | None:
    """Run a command and return its trimmed stdout, or None on failure."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def docker_server_version() -> str | None:
    return _first_line(["docker", "version", "--format", "{{.Server.Version}}"])


def compose_version() -> str | None:
    return _first_line(["docker", "compose", "version", "--short"])


def compose_version_supported(version: str | None) -> bool:
    """Return whether a detected Compose version satisfies the v2+ contract."""
    if not version:
        return False
    try:
        return int(version.lstrip("v").split(".", 1)[0]) >= 2
    except ValueError:
        return False
