# The canonical rc-repro skill and thin host adapters

Design for the versioned agent skill rc-repro ships and how hosts get it.
Resolves [Canepro/rc-repro#8](https://github.com/Canepro/rc-repro/issues/8). Planning only.

Builds on the [#3 research](https://github.com/Canepro/rc-repro/issues/3), which verified the
format and per-host discovery paths, plus the [#6](https://github.com/Canepro/rc-repro/issues/6)
contract and the [#7](https://github.com/Canepro/rc-repro/issues/7) grant model.

## Decisions

| # | Decision | Rejected alternative |
|---|---|---|
| D1 | One canonical bundle **inside the Python package**, materialised by `rc-repro skill install` | require a git checkout; publish the skill separately |
| D2 | **Copy plus digest**, drift detected and repaired by one idempotent command | symlink into the package; symlink-with-copy-fallback |
| D3 | Skill body is **task recipes**; every rule is delegated to `capabilities --json` and exit codes | a self-contained command and error reference |
| D4 | Two committed directories cover four hosts; **AGENTS.md and MCP get pointers, not copies** | per-host skill variants |

## D1: the bundle lives in the package

The plain user is a pipx user with no checkout (#3 research, verified against `README.md:55-59`).
So the canonical bundle ships as **package data** inside the installed distribution, and a CLI
verb materialises it:

```
rc-repro skill install [--host claude|codex|cursor|copilot|all] [--scope user|project] [--json]
rc-repro skill status [--json]
```

This makes version matching structural rather than aspirational: the bundle in the package is by
definition the one that shipped with the running rc-repro. There is no second place to publish
it, no separate release cadence, and no way for the skill to describe a version of rc-repro that
is not installed.

The repo also commits `.agents/skills/rc-repro/` and `.claude/skills/rc-repro/` for contributors
working from a checkout, generated from the same source so they cannot diverge. A test should
assert the committed copies match the packaged bundle byte for byte; otherwise this design
recreates the exact divergent-copy problem it exists to prevent.

## D2: copy plus digest

`skill install` copies the bundle and writes a sidecar next to it:

```json
{ "rc_repro_version": "0.9.3",
  "digest": "sha256:...",
  "installed_at": "2026-07-31T09:14:02+00:00",
  "host": "claude",
  "scope": "user" }
```

`capabilities --json` (from #6) reports installation state, so an agent discovers staleness
through the contract it already reads rather than through a second mechanism:

```json
{ "skill": { "installed": true, "state": "stale",
             "installed_version": "0.9.1", "running_version": "0.9.3",
             "repair": "rc-repro skill install" } }
```

`states`: `absent`, `current`, `stale` (version differs), `modified` (digest differs from what was
installed, meaning a human edited it). **`modified` is never silently overwritten**; `skill
install` reports it and requires `--force`, because clobbering someone's local edit is a small
betrayal that costs more trust than the staleness costs.

Symlinking was the tempting option, since it makes drift impossible rather than merely
detectable. It was rejected because the link breaks when pipx rebuilds or relocates the venv and
fails on Windows without developer mode, so it trades a detectable problem for a mysterious one.
The accepted cost of copying is a real window between upgrading rc-repro and repairing the skill,
which is why the state is surfaced in `capabilities` rather than left for the user to notice.

## D3: recipes, not a reference

This is the decision that actually answers the ticket's "without duplicating its lifecycle,
onboarding, authority, or evidence rules".

**The skill teaches judgement. rc-repro enforces rules.** Concretely, `SKILL.md` contains:

- **When to reach for rc-repro at all**, which is the part no contract can express: a reported bug
  that needs a version-matched environment, evidence for a support ticket, checking whether
  behaviour is version-specific.
- **Recipes for common jobs**, as sequences of intent rather than flag lists: reproduce a report
  at a version, capture evidence and tear down, keep a repro alive for a human to look at.
- **Three standing rules**, and nothing more:
  1. Read `rc-repro capabilities --json` before acting. It is the authority on commands, flags,
     phases, error codes, and exit codes for *this* build.
  2. Branch on `error.code` and exit codes, never on prose. Exit 6 means stop and ask the human,
     using the `approve_with` string verbatim.
  3. Never import rc-repro's Python internals and never scrape human output.

What `SKILL.md` deliberately does **not** contain: a flag reference, an error-code table, an
exit-code table, or the authority rules. All four live in `capabilities --json` and would rot in
prose. A skill that disagrees with the binary is worse than no skill, and the #3 research names
this as the divergent-copy failure, which duplicating the contract into skill content would
simply relocate from files into paragraphs.

The accepted cost: an agent makes one extra call before acting, and on a host where that call
cannot run the skill is vaguer than a self-contained one would be. That is the right trade, because
the failure mode of the alternative is silent wrongness rather than a missing call.

### Frontmatter

Restricted to the fields the published Agent Skills spec defines (`name`, `description`), per the
#3 research's rule for keeping one source canonical. Host-only fields stay out of the canonical
body, including Claude Code's extra fields, because the superset host is the fork risk here rather
than a gap.

`description` matters more than the body, since it is what triggers activation. It should name the
concrete situations (reproducing a Rocket.Chat bug at a specific version, needing a disposable
Rocket.Chat instance, collecting evidence for a ticket) rather than describe the tool abstractly.

## D4: adapters

From the #3 research's verified per-host table:

| Host | Adapter needed |
|---|---|
| Claude Code | copy into `~/.claude/skills/rc-repro/` or the project equivalent |
| OpenAI Codex | copy into `.agents/skills/rc-repro/` or `$HOME/.agents/skills`; alternatively register a path in `config.toml` with no filesystem work |
| Cursor | **none**, it reads `.claude/skills/` and `.codex/skills/` for compatibility |
| GitHub Copilot | **none** if the repo ships `.claude/skills/` or `.agents/skills/` |
| AGENTS.md-only hosts | a few prose lines naming the canonical `SKILL.md` path and when to read it |
| MCP-capable hosts | an MCP server returning the body or a `resource_link` |

The last two rows are **not adapters**. They are discovery hints for hosts with no skill
mechanism, and they must say "read this file" rather than restate anything. That constraint is the
whole reason they stay in this table rather than becoming a second skill format.

Known gaps, from the research: neither Codex nor Cursor has an `allowed-tools` equivalent, and
glob scoping is not portable. **rc-repro's safety gates are therefore enforced by rc-repro's own
exit codes, never by skill frontmatter.** This is the single most important portability
consequence: a host that cannot express tool restrictions is still safe, because authority lives
in the binary. Any design that leaned on frontmatter permissions would be secure only on Claude
Code.

## Relationship to Mira Workbench

The canonical skill is rc-repro's, and it must be usable by someone who has only rc-repro. Mira
Workbench remains a personal integration that consumes rc-repro, is never a dependency of it, and
is not contributed upstream. Nothing in this bundle may reference it.

## What this does not decide

- The prose of `SKILL.md` and its recipes, which is drafting work once the CLI surface from #6
  exists to write against.
- Whether to ship an MCP server at all, as opposed to documenting how someone else would. Not
  blocking.
- The implementation and review order, which is
  [#10](https://github.com/Canepro/rc-repro/issues/10).
