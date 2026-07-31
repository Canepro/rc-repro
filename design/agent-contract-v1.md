# rc-repro agent contract v1

Design for the versioned machine-readable surface an agent uses to drive rc-repro.
Resolves [Canepro/rc-repro#6](https://github.com/Canepro/rc-repro/issues/6). Planning
only: nothing here is implemented yet.

## Summary

Contract v1 is mostly a *closing and serializing* job, not new machinery. rc-repro
already has an internal progress event model (`rc_repro/services/events.py`), a shared
domain error taxonomy (`rc_repro/errors.py`), and one versioned payload
(`rc-repro.evidence.v1`). v1 promotes those three into a stable wire contract and fills
the three real gaps: no discovery call, no error codes, and no exit codes beyond `1`.

Four decisions were taken with Vincent:

| # | Decision | Rejected alternative |
|---|---|---|
| D1 | Streaming progress in v1, with a **closed** phase vocabulary both Docker and Kubernetes emit | blind-until-return; per-topology event types; free-text lines |
| D2 | **rc-repro** classifies terminal failures and aborts, with a distinct exit code | agent policy decides when to give up |
| D3 | `--json` on the **existing** verbs | a separate `rc-repro agent <verb>` namespace |
| D4 | **Wrapped** uniform envelope, bumping evidence to `v2` | bare per-command payloads; grandfathering evidence |

D1's rationale, in Vincent's terms: Kubernetes start-up time varies by preset, so a
fixed timeout is the wrong instrument. An agent that cannot see progress either kills a
healthy slow run or waits out one that was already dead.

## Starting point in the code

| Piece | Where it is today | What v1 does to it |
|---|---|---|
| Progress events | `services/events.py:15` `Event(message, phase, level, pct, data, terminal)` with `as_dict()` | keep the shape, **close** the phase set, serialize as NDJSON |
| Event consumers | CLI prints them (`cli.py:136`); web API buffers per job and pushes over SSE (`events.py:6`) | both front-ends serialize the *same* dict, so CLI and GUI cannot drift |
| Error taxonomy | `errors.py:18-45` `ReproError` subclasses carrying `http_status` | add a stable `code`, derive exit codes from the same classes |
| Failure exit | `typer.Exit(1)` at every site (`cli.py:603`, `1346`, `1699`) | exit-code map below |
| Versioned payload | `rc-repro.evidence.v1` (`runner.py:192`) | becomes `evidence.v2` inside the envelope |
| Existing `--json` | `evidence` (flag accepted then discarded, `cli.py:528-535`), `loadtest`, `capacity` (ad-hoc, no `schema`) | brought under the envelope |

The `Event.data` carrying the Result on `terminal=True` (`events.py:22`) is already the
"stream then final object" pattern this contract needs. v1 formalizes it rather than
replacing it.

## Contract identity and versioning

Two independent version numbers, because they answer different questions:

- `contract`: an integer, the **wire** contract generation. Bumped only on a breaking
  change to the envelope, the phase vocabulary, the error-code set, or the exit-code map.
  An agent refusing to run against an unknown `contract` is the intended behavior.
- `schema`: `rc-repro.<kind>.v<n>`, versioning each **payload** independently, continuing
  the existing `rc-repro.evidence.v1` convention. `up.v1`, `ready.v1`, `evidence.v2`.

Additive changes are not breaking: new optional `data` keys, new `warnings` entries, new
`detail` keys. Agents must ignore unknown keys. Removing or retyping a key, or emitting a
phase or error code outside the published set, is breaking.

`rc_repro_version` also rides in every reply so evidence and bug reports pin the build.

## Surface (D3)

`--json` on the existing verbs. The agent uses the same commands a human uses, so the
agent path stays exercised by ordinary use and there is one thing to document.

```
rc-repro capabilities --json
rc-repro doctor --json
rc-repro up --preset microservices --version 8.6.1 --json
rc-repro ready rc-861 --json
rc-repro info rc-861 --json
rc-repro list --json
rc-repro evidence rc-861
rc-repro down rc-861 --json
```

The accepted cost: human-facing flag names become part of a stability promise. Mitigation
is that `capabilities` (below) publishes the flags an agent may rely on, so the promise
covers a declared subset rather than the entire CLI by accident.

## Envelope (D4)

Every non-streaming JSON reply, success or failure, on stdout:

```json
{
  "schema": "rc-repro.up.v1",
  "contract": 1,
  "rc_repro_version": "0.9.3",
  "generated_at": "2026-07-31T09:14:02+00:00",
  "ok": true,
  "data": {
    "name": "rc-861",
    "preset": "microservices",
    "topology": "kubernetes",
    "rc_version": "8.6.1",
    "state": "running",
    "root_url": "http://localhost:3000",
    "booted_s": 214
  },
  "warnings": [
    { "code": "ENGINE_KERNEL_MONGO8", "message": "engine kernel 6.19.7: MongoDB 8.0 will not start (SERVER-121912)" }
  ],
  "error": null
}
```

Rules: `ok` is the single authority on success. `data` is `null` when `ok` is false.
`error` is `null` when `ok` is true. `warnings` is always an array, never `null`, and
never fatal. Every `warnings` entry has a stable `code`, so an agent can branch without
reading English. `warnings` is populated from `level="warn"` events, which is how
`cli.py:1056`'s existing "collect warnings into the JSON payload" behavior generalizes.

`evidence` becomes `rc-repro.evidence.v2`: today's body moves wholesale under `data`,
unchanged field for field. That is a breaking change to a shipped schema and needs calling
out in release notes. It is worth it because the alternative is a permanent exception the
next contributor copies.

## Event stream (D1)

`--json` on a long-running verb emits **NDJSON on stdout**: one JSON object per line, one
event per line, and the final line is the envelope above. This is the serialization of
`Event.as_dict()` plus a `schema`, so no second event model exists.

```
{"schema":"rc-repro.event.v1","contract":1,"phase":"preflight","level":"info","pct":0,"message":"checking engine and ports","data":{}}
{"schema":"rc-repro.event.v1","contract":1,"phase":"resolve","level":"info","pct":5,"message":"resolved 8.6.1 to chart 6.10.2","data":{"chart_version":"6.10.2"}}
{"schema":"rc-repro.event.v1","contract":1,"phase":"provision","level":"info","pct":10,"message":"creating cluster rc-repro-local","data":{"topology":"kubernetes"}}
{"schema":"rc-repro.event.v1","contract":1,"phase":"pull","level":"info","pct":40,"message":"pulling rocketchat/rocket.chat:8.6.1","data":{"image":"rocketchat/rocket.chat:8.6.1"}}
{"schema":"rc-repro.event.v1","contract":1,"phase":"boot","level":"info","pct":60,"message":"starting mongodb","data":{"component":"mongodb"}}
{"schema":"rc-repro.event.v1","contract":1,"phase":"wait","level":"info","pct":80,"message":"waiting for Rocket.Chat health","data":{"elapsed_s":31}}
{"schema":"rc-repro.up.v1","contract":1,"ok":true,"data":{"name":"rc-861","state":"running","booted_s":214},"warnings":[],"error":null}
```

Guarantees an agent may rely on:

1. Exactly one envelope object, and it is the last line. Its `schema` is never
   `rc-repro.event.v1`.
2. `phase` is drawn from the closed set below. An unrecognized `phase` means the contract
   generation is newer than the agent, and the agent should treat it as opaque progress,
   not an error.
3. `pct` is monotonic non-decreasing within a run, or `null` when genuinely unknown.
   Never fabricate a percentage.
4. Human-readable prose lives only in `message`. Machine decisions read `phase`, `level`,
   `code`, and `data`.
5. Anything rc-repro writes to stderr is diagnostics for humans. An agent parsing stderr
   is out of contract.

### Closed phase vocabulary v1

Deliberately the existing informal names from `events.py:18` (`pull|boot|wait|post_ready|
seed|restore|done`) rather than a fresh set, so the upstream diff is small and the GUI's
current stream stays valid. The additions are the phases that only exist once preflight
and Kubernetes are real.

| Phase | Meaning | Docker | Kubernetes |
|---|---|---|---|
| `preflight` | engine, versions, disk, ports, connectivity checks | yes | yes |
| `resolve` | version, preset, chart and image resolution | yes | yes |
| `provision` | create or verify the execution target itself | no | yes (cluster) |
| `pull` | fetching images | yes | yes |
| `boot` | starting components | yes | yes |
| `wait` | waiting for readiness or health | yes | yes |
| `post_ready` | settings applied after Rocket.Chat serves | yes | yes |
| `seed` | seeding users, channels, messages | yes | yes |
| `restore` | restoring data into a repro | yes | yes |
| `teardown` | stopping and removing | yes | yes |
| `done` | the run finished successfully | yes | yes |
| `failed` | terminal failure, always carries `data.code` | yes | yes |
| `info` | uncategorized progress, existing default, never branch on it | yes | yes |

Kubernetes emits a **superset** of Docker's phases, not a different vocabulary. That is
what makes one agent code path work against both topologies, which is the whole point of
the map's shared-lifecycle goal.

Load-test and capacity runs keep their existing `k6` phase under `info` semantics; those
verbs already emit JSON and are out of v1's lifecycle scope.

## Errors and fail-fast (D2)

### Error payload

```json
{
  "schema": "rc-repro.error.v1",
  "contract": 1,
  "rc_repro_version": "0.9.3",
  "ok": false,
  "data": null,
  "warnings": [],
  "error": {
    "code": "IMAGE_PULL_AUTH_FAILED",
    "message": "denied: requested access to the resource is denied",
    "phase": "pull",
    "remedy": "docker login, or set a registry credential; Docker Hub anonymous pulls are rate limited",
    "gate": null,
    "detail": { "image": "rocketchat/rocket.chat:8.6.1" }
  }
}
```

`code` is a stable SCREAMING_SNAKE identifier and is the only field an agent branches on.
`message` is free prose and may change between releases. `remedy` is a hint for the human
the agent reports to. `gate` is non-null only for exit 6 (below).

The clean implementation seam: give each `ReproError` subclass a `code` class attribute
alongside its existing `http_status` (`errors.py:18-45`). One taxonomy then feeds three
consumers, the CLI exit code, the HTTP status, and the JSON `error.code`, with no
duplicated mapping table.

### Exit codes

| Exit | Meaning | Source error | Agent's correct response |
|---|---|---|---|
| 0 | success | | continue |
| 1 | unexpected internal failure | uncaught | stop, capture evidence, escalate to the human |
| 2 | bad input or usage | `ValidationError` | fix the call, do not retry unchanged |
| 3 | preflight or engine failure | `DockerError` | run `doctor --json`, report, stop |
| 4 | no such repro | `NotFoundError` | stop |
| 5 | not ready within timeout | `NotReadyError` | may poll again or give up on policy |
| 6 | human authority gate | `AuthorityGateError` (new) | **stop and ask the human**, never retry |
| 7 | create failed, terminal | `CreateFailedError` (new) | stop, capture evidence, do not retry blindly |
| 8 | conflict, name or port taken | `ConflictError` | pick another name or port, retry once |

Exit 5 and exit 7 are deliberately distinct. That distinction is the machine-readable form
of D1's rationale: 5 means "still unknown, the clock ran out", 7 means "known dead, stop
now". Collapsing them is what makes agents waste four minutes on a dead run.

### Fail-fast behavior

On a condition rc-repro classifies as terminal, it emits a `failed` event carrying
`data.code`, stops waiting immediately, and exits 7. It does not wait out `--timeout`.

The accepted risk, stated plainly: rc-repro now owns a classification table that will
sometimes be wrong, and misclassifying a transient condition as terminal aborts a run that
would have recovered. Two guards. First, the table starts small and only holds conditions
that cannot self-heal (registry auth denied, image manifest not found, a component that
exited non-zero and is not restarting, an unschedulable pod with no matching node).
Second, restart-and-retry conditions are explicitly *not* terminal in v1; a `CrashLoopBackOff`
becomes terminal only after a published threshold, which is a Kubernetes-shaped decision
and is deferred to its own ticket rather than guessed here.

### Authority gates

The map's human gates (public exposure, unapproved clusters, new credentials, unowned
deletion, unapproved retention) surface as exit 6 with a machine-readable gate:

```json
{ "code": "GATE_UNAPPROVED_CLUSTER",
  "message": "cluster 'prod-eu' is not an approved Kubernetes target for rc-repro",
  "gate": { "kind": "cluster", "subject": "prod-eu", "approve_with": "rc-repro use --cluster prod-eu" } }
```

Exit 6 is never retryable and never auto-approvable by an agent. `approve_with` tells the
agent what to *ask the human to run*, not what to run itself. This is the enforcement
point for the map's "persisted preferences give standing authority within scope" note: the
gate fires precisely when a request falls outside persisted scope.

## Discovery: `rc-repro capabilities --json`

The one genuinely new verb. It is what makes a version-matched skill possible: the skill
asks what this build can do instead of probing and guessing.

```json
{
  "schema": "rc-repro.capabilities.v1",
  "contract": 1,
  "rc_repro_version": "0.9.3",
  "ok": true,
  "data": {
    "contract_versions": [1],
    "commands": [
      { "name": "up", "schema": "rc-repro.up.v1", "streams": true,
        "flags": ["--name","--preset","--version","--rc-tag","--port","--bind","--json"] },
      { "name": "ready", "schema": "rc-repro.ready.v1", "streams": false, "flags": ["--name","--timeout","--json"] },
      { "name": "down", "schema": "rc-repro.down.v1", "streams": true, "flags": ["--name","--volumes","--yes","--json"] },
      { "name": "evidence", "schema": "rc-repro.evidence.v2", "streams": false, "flags": ["--name"] }
    ],
    "phases": ["preflight","resolve","provision","pull","boot","wait","post_ready","seed","restore","teardown","done","failed","info"],
    "error_codes": ["VALIDATION_FAILED","NOT_FOUND","CONFLICT_NAME","CONFLICT_PORT","ENGINE_UNAVAILABLE","IMAGE_PULL_AUTH_FAILED","NOT_READY_TIMEOUT","CREATE_FAILED","GATE_UNAPPROVED_CLUSTER","GATE_PUBLIC_EXPOSURE","GATE_RETENTION","GATE_DELETE_UNOWNED"],
    "exit_codes": { "0":"ok","1":"internal","2":"usage","3":"preflight","4":"not_found","5":"not_ready","6":"gate","7":"create_failed","8":"conflict" },
    "topologies": ["compose-single","compose-multi","kubernetes-microservices"],
    "presets": ["default","ldap","saml","email","s3","microservices"],
    "gates_enforced": ["public_exposure","unapproved_cluster","new_credentials","delete_unowned","retention"]
  }
}
```

`capabilities` must be answerable **offline and without an engine**, since a skill calls it
before knowing whether the environment works. Preflight belongs to `doctor --json`, not
here. The `topologies` and `presets` lists above are illustrative; their real contents come
from the preset catalog and from tickets #4 and #5.

`doctor --json` returns the same envelope with per-check results carrying stable check ids
and `ok|warn|fail`, plus the existing counts. It is the agent's preflight call, and exit 3
on `fail` is what tells an agent to stop before attempting `up`.

## One wire format for CLI and GUI

Because both the CLI's NDJSON and the web API's SSE frames serialize the same
`Event.as_dict()`, they are the same wire format with different transports. This is
recorded as a constraint, not left to chance: a change to the event contract must update
both front-ends together, and the GUI is a consumer of the same contract an agent uses.

## What v1 does not decide

Left to other tickets rather than guessed here:

- The terminal-versus-transient classification table, including the `CrashLoopBackOff`
  threshold. Kubernetes-shaped, blocked on how Kubernetes joins the lifecycle.
- Which verbs get `--json` in which order, and how the work splits into reviewable
  upstream changes. That is the implementation-sequence ticket.
- Cleanup handle and retention semantics beyond the gate code. That is the evidence,
  retention and ownership ticket.
- The concrete `presets` and `topologies` values, which follow from the Kubernetes runtime
  and lifecycle tickets.
