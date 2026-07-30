# Portable agent-skill format and installation adapters

Research date: 2026-07-31

## Decision-ready answer

Use the [Agent Skills open specification](https://agentskills.io/specification)
as the only canonical skill format. Ship one `rc-repro/` skill directory inside
the rc-repro Python distribution, then install that directory unchanged into
each agent host's documented discovery location. The specification defines a
directory containing `SKILL.md`, with optional `scripts/`, `references/`, and
`assets/`; `SKILL.md` has YAML frontmatter and Markdown instructions. OpenAI
states that Codex skills build on this standard, and Anthropic states that
Claude Code follows it while adding host-specific extensions.
([Agent Skills specification](https://agentskills.io/specification),
[OpenAI Codex skills](https://developers.openai.com/codex/skills),
[Claude Code skills](https://code.claude.com/docs/en/skills))

The minimal initial adapter set should be:

- Install one byte-identical copy at `~/.agents/skills/rc-repro` for Codex,
  GitHub Copilot, and Gemini CLI. All three products officially recognize that
  user-level location.
  ([Codex discovery](https://developers.openai.com/codex/skills#where-codex-loads-local-skills),
  [GitHub Copilot locations](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills#creating-and-adding-a-skill),
  [Gemini CLI discovery](https://geminicli.com/docs/cli/using-agent-skills/#discovery-tiers))
- Install the same directory at `~/.claude/skills/rc-repro` for Claude Code,
  whose documented personal location is host-specific.
  ([Claude Code locations](https://code.claude.com/docs/en/skills#where-skills-live))
- Provide equivalent project-scope destinations, `.agents/skills/rc-repro` and
  `.claude/skills/rc-repro`, but keep user scope as the normal choice for a
  locally installed command-line tool used across repositories. These are
  documented project locations for the corresponding hosts.
  ([Codex discovery](https://developers.openai.com/codex/skills#where-codex-loads-local-skills),
  [Claude Code locations](https://code.claude.com/docs/en/skills#where-skills-live),
  [GitHub Copilot locations](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills#creating-and-adding-a-skill),
  [Gemini CLI discovery](https://geminicli.com/docs/cli/using-agent-skills/#discovery-tiers))

This is a compatibility strategy, not a claim of universal compatibility.
Discovery paths, invocation syntax, permission behavior, plugins, and
host-specific frontmatter remain product contracts rather than parts of the
common format. That boundary is an inference from the format specification
defining the skill package while each host separately documents discovery and
extensions.

## Confirmed portable contract

The canonical `SKILL.md` should use only the common specification:

```yaml
---
name: rc-repro
description: >-
  Operate disposable, version-matched Rocket.Chat reproduction environments
  with rc-repro. Use for setup, deployment, verification, evidence capture,
  diagnosis, retention, and teardown through the public rc-repro CLI.
license: MIT
compatibility: Requires the rc-repro CLI and the runtime selected during onboarding.
---
```

The proposed `license` value matches rc-repro's
[MIT repository license](../../LICENSE).

The specification requires `name` and `description`, requires the `name` to
match the parent directory, and permits `license`, `compatibility`, `metadata`,
and the experimental `allowed-tools` field.
([Agent Skills frontmatter](https://agentskills.io/specification#frontmatter))

Keep detailed command contracts and onboarding behavior in referenced Markdown
files, using relative paths from the skill root. The standard explicitly
supports referenced resources and recommends progressive disclosure rather
than placing all detail in `SKILL.md`.
([Agent Skills file references](https://agentskills.io/specification#file-references),
[Agent Skills progressive disclosure](https://agentskills.io/specification#progressive-disclosure))

Do not use any of these in the portable core:

- `allowed-tools`: it is experimental and support may vary between
  implementations. GitHub also warns that pre-approving shell access removes a
  confirmation boundary.
  ([Agent Skills `allowed-tools`](https://agentskills.io/specification#allowed-tools-field),
  [GitHub shell warning](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills#enabling-a-skill-to-run-a-script))
- Claude-only fields or syntax such as `disable-model-invocation`, `context`,
  `agent`, dynamic command injection, or Claude substitutions. Anthropic
  describes those as Claude Code extensions to the open standard.
  ([Claude Code extensions](https://code.claude.com/docs/en/skills),
  [Claude Code invocation controls](https://code.claude.com/docs/en/skills#control-who-invokes-a-skill),
  [Claude Code dynamic context](https://code.claude.com/docs/en/skills#inject-dynamic-context))
- OpenAI-only `agents/openai.yaml` in the portable core. OpenAI documents it as
  optional UI, policy, and dependency metadata, so it can be added by a Codex
  packaging adapter later without changing `SKILL.md`.
  ([OpenAI optional metadata](https://developers.openai.com/codex/skills#optional-metadata))

The skill must describe operations through rc-repro's public CLI and
machine-readable output. It must not import rc-repro's Python internals or
encode a second set of user preferences. This is a design recommendation:
keeping behavior and authorization in the versioned CLI/config contract makes
the same instructions meaningful across hosts whose tool and permission models
differ.

## Canonical source and release coupling

Place the canonical bundle at:

```text
rc_repro/data/agent-skills/rc-repro/
├── SKILL.md
└── references/
    ├── onboarding.md
    └── lifecycle.md
```

This location is a recommendation based on rc-repro's existing packaging:
`pyproject.toml` already ships runtime resources from `rc_repro/data/`.
The implementation would add the new recursive package-data pattern rather
than create a separately versioned skill repository.
([rc-repro package-data configuration](../../pyproject.toml))

The installed skill version should be the rc-repro package version that
contains it. Do not maintain an independent skill version unless the skill
later gains a release lifecycle independent of the CLI. A build test should
assert that the wheel contains the canonical directory, preventing a source
release whose skill disappears from the installed package.

An installation record under the existing rc-repro home should track:

```yaml
schema_version: 1
rc_repro_version: 0.18.0
skill_sha256: "<digest of canonical directory>"
destinations:
  - host_family: agents
    path: "~/.agents/skills/rc-repro"
  - host_family: claude-code
    path: "~/.claude/skills/rc-repro"
```

The version shown is illustrative. The implementation should derive it from
the installed package rather than copy a literal version into two maintained
sources.

## Thin installation adapter

Add one rc-repro-owned installer interface rather than separate rewritten
skills:

```text
rc-repro skill install --host auto --scope user
rc-repro skill status --json
rc-repro skill sync
rc-repro skill uninstall
```

These command names are a proposed interface, not an existing rc-repro
contract. The adapter should:

1. Detect installed hosts and show one compact first-use proposal.
2. Persist the accepted destinations once, alongside rc-repro onboarding
   preferences.
3. Copy the canonical bundle byte-for-byte to the selected destinations.
4. Record the package version and content digest.
5. Update an unmodified managed copy atomically when rc-repro is upgraded.
6. Refuse to overwrite a locally modified copy without an explicit repair or
   force action.
7. Keep user onboarding choices in rc-repro's existing configuration, not in
   Codex-, Claude-, Copilot-, or Gemini-specific files.

Copying should be the default release mechanism. Symlinks are useful for skill
development, and Codex and recent Claude Code officially support symlinked
skill directories, while Gemini CLI exposes a link command. A managed copy is
the more conservative cross-platform release default because the common
standard itself does not specify symlink behavior.
([Codex symlink support](https://developers.openai.com/codex/skills#where-codex-loads-local-skills),
[Claude Code symlink support](https://code.claude.com/docs/en/skills#where-skills-live),
[Gemini CLI link command](https://geminicli.com/docs/cli/using-agent-skills/#link-for-development))

GitHub CLI's `gh skill` can install for a named agent, pin a tag or commit, and
record provenance for updates. It is a useful optional distribution path once
the skill is published in the upstream repository, but GitHub marks the command
as public preview, so the first rc-repro release should not require it.
([GitHub skill installation and pinning](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills#installing-skills),
[GitHub preview status](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills#managing-skills-with-github-cli))

## Host compatibility matrix

| Host | Confirmed format and discovery | Initial adapter decision |
| --- | --- | --- |
| OpenAI Codex | OpenAI says skills build on the open Agent Skills standard. Codex scans repository and user `.agents/skills` locations and supports symlinked skill folders. [Official docs](https://developers.openai.com/codex/skills) | Supported through the shared `.agents` destination. A Codex plugin or `agents/openai.yaml` may improve install/UI integration later, but neither is required for the portable core. OpenAI recommends plugins for reusable distribution, so marketplace publication can be a later adapter rather than a fork of the skill. |
| Claude Code | Anthropic says Claude Code follows Agent Skills and adds product-specific extensions. It discovers personal `~/.claude/skills` and project `.claude/skills`; recent versions support symlinked skill directories. [Official docs](https://code.claude.com/docs/en/skills) | Supported through the Claude-specific destination with the unchanged canonical bundle. Do not use Claude extensions in the common `SKILL.md`. |
| GitHub Copilot | GitHub supports Agent Skills across its cloud agent, code review, CLI, app, VS Code, and documents `.agents/skills` for repository and personal use. [Official docs](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills) | Supported through the shared `.agents` destination. `gh skill` is an optional preview installer, not a required dependency. |
| Gemini CLI | Gemini CLI documents user and workspace `.agents/skills` as aliases for its native `.gemini/skills` locations and provides install/link commands. [Official docs](https://geminicli.com/docs/cli/using-agent-skills/) | Supported through the shared `.agents` destination. Its documented per-activation consent remains a host policy and must not be bypassed by the skill. |
| Cursor | Cursor describes `SKILL.md`-based Agent Skills, but its current official best-practices page says the feature is available only in the nightly channel. [Official Cursor guidance](https://cursor.com/blog/agent-best-practices#extending-the-agent) | Experimental only. Do not promise initial support or add a stable adapter until Cursor publishes a stable discovery/install contract and rc-repro tests it. |

“Supported” in this table is a proposed rc-repro support target based on
documented host contracts. It becomes a release claim only after the acceptance
tests below pass against declared host versions.

## Validation and acceptance

The contribution should gate the canonical bundle with the reference
`skills-ref validate` command published by the Agent Skills specification.
([Agent Skills validation](https://agentskills.io/specification#validation))

Before declaring a host supported, test all of the following:

1. Build both the wheel and source distribution and prove the canonical bundle
   is present.
2. Install into an isolated home directory for each adapter family and verify
   that every installed file matches the canonical digest.
3. Use the host's own skill listing or inspection surface to prove that
   `rc-repro` was discovered.
4. Test explicit invocation and a natural-language request that should trigger
   the skill.
5. Test a nearby request that should not trigger it.
6. Verify that the skill calls only the public rc-repro CLI/JSON contract.
7. Verify first-use onboarding persists approved choices and a later run does
   not repeat the interview.
8. Verify the agent tears down a reproduction it created by default, while
   refusing to delete a reproduction whose ownership cannot be proved.
9. Upgrade rc-repro and prove an unmodified managed skill updates, while a
   locally modified copy is preserved and reported as a conflict.

Record the tested host name and minimum version in rc-repro's compatibility
documentation. Host behavior can change independently of the Agent Skills
format, so this matrix needs periodic reconciliation against first-party docs
and smoke tests.

## Limits of this recommendation

- The common format does not make tool names, shell permissions, approval
  models, invocation syntax, or marketplaces portable.
- A skill is instruction and resource packaging, not an enforcement boundary.
  rc-repro itself must enforce ownership, target selection, network exposure,
  retention, and teardown safety.
- ChatGPT/Codex plugins, Claude Code plugins, Gemini extensions, and GitHub
  Copilot plugins are separate distribution systems. They may wrap the same
  canonical skill later, but they should not become independently authored
  copies.
- Hosts not listed above are unverified. A `SKILL.md` feature or community
  installer is insufficient evidence for a support claim without an official
  contract and a reproducible discovery test.

## Sources

Only primary sources were used:

- [Agent Skills specification](https://agentskills.io/specification)
- [OpenAI: Build skills for ChatGPT and Codex](https://developers.openai.com/codex/skills)
- [Anthropic: Extend Claude with skills](https://code.claude.com/docs/en/skills)
- [GitHub: Adding agent skills for GitHub Copilot](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills)
- [Google: Managing Agent Skills in Gemini CLI](https://geminicli.com/docs/cli/using-agent-skills/)
- [Cursor: Best practices for coding with agents](https://cursor.com/blog/agent-best-practices#extending-the-agent)
- [rc-repro packaging configuration](../../pyproject.toml)
