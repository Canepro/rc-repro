# One-time onboarding and persisted preference semantics

Design for the onboarding step and the preferences it persists.
Resolves [Canepro/rc-repro#7](https://github.com/Canepro/rc-repro/issues/7). Planning only.

This ticket had commitments made *for* it by two earlier decisions: [#4](https://github.com/Canepro/rc-repro/issues/4)
put engine-resize consent into onboarding, and [#6](https://github.com/Canepro/rc-repro/issues/6)
made persisted authority the thing exit 6 checks against. This design consolidates those rather
than inventing new mechanisms.

## Decisions

| # | Decision | Rejected alternative |
|---|---|---|
| D1 | Interactive onboarding is human-only, but **every answer is settable non-interactively** in one command; an agent on an un-onboarded machine exits 6 pointing at it | gate piecemeal with no onboarding; let the agent self-onboard |
| D2 | **Namespaced, additive-only** keys in the existing flat `config.yaml`, no version field, no migration code | `config_version` plus a migration step |
| D3 | **Silent revalidation** every run; a question returns only when a *grant* is missing or an *assumption is contradicted* | re-confirm periodically; never re-ask |
| D4 | Secrets are **not** written to `config.yaml` by onboarding, and the file is written `0600` | keep current default-umask behaviour |

## Starting point

`config.yaml` today (`rc_repro/config.py`):

- A **flat dict** with no schema and no version key (`load_config`, `config.py:99`).
- `load_config(with_env=True)` layers three env overrides on top: `reg_token`, `rc_image`,
  `bind_host` (`config.py:68-72`). `with_env=False` exists specifically so ephemeral env values
  are not persisted on write-back, which is a careful existing design worth preserving.
- `save_config` writes with **default umask and no `chmod`** (`config.py:120-122`), while
  `reg_token` is a supported key. So a registration token can land in a world-readable file
  today. D4 addresses this.

## D1: one command, two front doors

Onboarding asks a human a small set of questions once. Every one of those answers is also
settable without a TTY, so a human can bless a machine in a single command and an agent then
runs silently forever.

```bash
# interactive, for a human at a terminal
rc-repro onboard

# non-interactive, the whole thing in one line
rc-repro onboard --accept-defaults --grant engine-resize
```

An agent that finds no completed onboarding does **not** guess and does not proceed. Per the #6
contract:

```json
{ "schema": "rc-repro.error.v1", "ok": false,
  "error": { "code": "GATE_NOT_ONBOARDED",
             "message": "rc-repro has not been onboarded on this machine",
             "gate": { "kind": "onboarding", "subject": "<hostname>",
                       "approve_with": "rc-repro onboard --accept-defaults --grant engine-resize" } } }
```

Exit 6, never retryable, never auto-approvable. `approve_with` tells the agent what to **ask the
human to run**, not what to run itself.

The accepted cost: two front doors to the same state, which can drift. Mitigation is that the
interactive flow is a thin wrapper that collects answers and calls the same writer the flags do,
so there is one code path and two input methods.

### What onboarding asks

Deliberately minimal. Every question here exists because some other decision needs it, and
nothing is asked that has a safe default:

| Question | Default | Why it must be asked |
|---|---|---|
| May rc-repro stop, resize, and restart your container engine VM when a preset needs capacity? | **no** | #4. Restarting the engine stops unrelated containers, so it cannot be assumed. |
| Which Kubernetes target may the `microservices` preset use? | rc-repro-owned local cluster | An existing named cluster is an explicit opt-in; ambient `kubectl` context is never used implicitly. |
| Retain runs by default, or tear down after evidence capture? | **tear down** | Retention costs disk and leaves workspaces behind. |

Everything else stays an opinionated default and is not a question. rc-repro's value is having
opinions, and an onboarding wizard that asks about admin passwords or bind hosts would erode
that.

The engine-resize prompt must state plainly that restarting the engine stops unrelated
containers. That is the real cost, and burying it is what makes a months-old yes feel like a
betrayal later.

## D2: namespaced, additive-only

```yaml
# existing keys, untouched
rc_image: registry.rocket.chat/rocketchat/rocket.chat
bind_host: 127.0.0.1

# added by onboarding
onboarding:
  completed_at: "2026-07-31T09:14:02+00:00"
  rc_repro_version: "0.9.3"
grants:
  engine_resize: true
  clusters: ["rc-repro-local"]
preferences:
  retain_runs: false
  kubernetes_target: "owned-local"
```

Rules that make this safe without a version field:

- **Never rename, retype, or remove an existing key.** New meaning gets a new key.
- **Unknown keys are ignored on read**, so a newer rc-repro's config stays loadable by an older
  one.
- **Absent means default**, so a file written before onboarding existed is valid, not "version 0".
- `load_config(with_env=False)` remains the writer's entry point so env values are never
  persisted.

Rejected `config_version` plus migration because the change is purely additive today, and a
buggy migration corrupting a working config is a worse failure than the problem it guards
against. The honest cost of that choice: without a version field there is nothing to detect a
future breaking change by, so the additive-only promise has to actually hold. If it is ever
broken, `config_version` gets added *then*, and its absence correctly means "pre-versioning".

## D3: silent revalidation, and what breaks the silence

Every run revalidates the environment. It does not re-ask settled questions. The distinction
that matters:

| Situation | Behaviour |
|---|---|
| Environment matches what was recorded | silent, no output beyond normal events |
| Environment changed but the grant still covers it (engine has more memory than before) | silent, emit a `preflight` event |
| A required grant is **missing** (resize needed, never granted) | exit 6 with `approve_with` |
| A recorded assumption is **contradicted** (a granted cluster no longer exists) | exit 6, naming the specific stale grant |
| A grant covers something now impossible (resize granted, engine no longer supports it) | exit 3 preflight failure, not a re-ask |

The last two rows are the point of D3. "Never repeat a settled question" cannot mean "never
speak again": a grant referring to a cluster that has been deleted is not settled, it is stale,
and silently proceeding would be worse than asking. But a *contradiction* is a different event
from an *unanswered question*, and only contradictions reopen anything.

Revalidation must be cheap enough to run unconditionally. It reads config, checks engine
reachability and capacity, and verifies granted clusters still exist. It must not pull images or
contact the network beyond the engine.

## D4: no secrets in config.yaml

Onboarding never writes a registration token, licence, or password into `config.yaml`.

- Registration tokens keep their existing route: the `RC_REPRO_REG_TOKEN` env override
  (`config.py:69`) or the `--reg-token` flag, both ephemeral.
- `save_config` should write the file `0600`. It currently uses default umask, so this is a
  small correctness fix worth carrying upstream on its own merits, independent of this design.
- If onboarding ever needs to remember *that* a token exists, it stores a boolean, never the
  value.

## Interaction with the agent skill

The skill (ticket [#8](https://github.com/Canepro/rc-repro/issues/8)) does not parse
`config.yaml`. It calls `rc-repro capabilities --json` from #6, which reports whether onboarding
is complete and which grants are enforced. That keeps the config file an implementation detail
rather than a second contract, which is the whole reason #6 exists.

## What this does not decide

- The exact wording of the interactive prompts, which is a prototype concern once there is
  something to run.
- How grants are revoked. Editing `config.yaml` works, but whether there should be a
  `rc-repro onboard --revoke` is not settled and is not blocking.
- Retention and cleanup-handle semantics beyond the `retain_runs` default, which is
  [#9](https://github.com/Canepro/rc-repro/issues/9).
