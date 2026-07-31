# Portable agent-skill format and installation adapter strategy

Research for Wayfinder ticket [#3](https://github.com/Canepro/rc-repro/issues/3): "Determine the
portable agent-skill format and installation adapter strategy". Planning only. Nothing is built here.

Date of source checks: 2026-07-31. Every claim below is either **[verified]** (I fetched the primary
source or ran the command myself in this session) or **[inference]** (my reasoning on top of verified
facts). Claims relayed from a subagent without my own check are marked **[unverified]**.

There is no existing `research/` or `docs/` directory in the repository ([verified] `git ls-files`
returns 80 paths, of which only `README.md` and `CONTRIBUTING.md` are Markdown), so this file
establishes `research/` as the convention for Wayfinder research output.

## Answer in one paragraph

Adopt the **Agent Skills open standard** (`SKILL.md` with `name` + `description` frontmatter, plus
`references/`, `scripts/`, `assets/`) as the canonical format, and restrict the frontmatter to the
fields the published spec defines. The premise of the ticket is now weaker than the map assumed, in a
good way: all five agent hosts I checked (Claude Code, OpenAI Codex, GitHub Copilot, Gemini CLI, and
Cursor) read that exact file format and layout from disk, so there is **no format to translate and no
divergent copy to maintain**. What remains is a *directory placement* problem plus a *version
stamping* problem. Two destinations cover every host: `.agents/skills/rc-repro/` is read by Codex,
Copilot, Gemini CLI, and Cursor, and `.claude/skills/rc-repro/` is read by Claude Code, Copilot, and
Cursor. Add one `rc-repro skill install` subcommand for the pipx user who has no repository checkout,
and the strategy is complete. Two caveats bound the answer: Cursor's own blog says Agent Skills are
nightly-only (section 3), and the genuinely non-portable parts are tool permissioning and glob
scoping, so rc-repro's safety gates must be enforced by rc-repro's CLI rather than declared in
frontmatter (section 7, item 4).

This file holds the primary answer for ticket #3, but it is **not** the only findings file on this
branch. An earlier commit (`5fae92b`) put a parallel, independent read at
`docs/research/agent-skill-portability.md`. Consolidation into a single file was started and never
finished: the research agent hit a spend limit mid-merge, so roughly 17 citations that exist only in
the `docs/` copy, including the `agentskills.io` specification anchors and the Gemini CLI and Copilot
skill docs, are **not** present here. Both reads reach the same conclusion on format and adapters, so
the decision stands, but merging the two files into one canonical artifact is outstanding work. Two
files answering one ticket is the divergent-copy failure this ticket is about, and that irony is
noted rather than hidden.

## 1. Recommended canonical format, and why

**Recommendation: the Agent Skills open standard as published at agentskills.io, using only its own
field set.**

Three reasons, in order of weight.

**Reason 1: it is a published standard, not a vendor format, and the hosts converged on it.**
Claude Code's own documentation says "Claude Code skills follow the [Agent
Skills](https://agentskills.io) open standard, which works across multiple AI tools. Claude Code
extends the standard with additional features" ([verified]
https://code.claude.com/docs/en/skills.md). GitHub says "The Agent Skills specification is an
[open standard](https://github.com/agentskills/agentskills)" ([verified]
https://docs.github.com/en/copilot/concepts/agents/about-agent-skills). Cursor says "Agent Skills is
an open standard. Learn more at agentskills.io" ([verified] https://cursor.com/docs/context/skills).
Codex documents "Skills use the Agent Skills standard with a mandatory `SKILL.md` file" ([verified]
https://learn.chatgpt.com/docs/build-skills).

**Reason 2: the format already carries the two things the map requires.** Progressive disclosure
lets the skill stay small at rest and load detail on demand, and `metadata` gives a
standard-sanctioned place to stamp the rc-repro version (section 4).

**Reason 3: the alternative formats are strictly weaker.** `AGENTS.md` is "just standard Markdown"
with no frontmatter, no schema, and no on-demand loading ([verified] https://agents.md/), so it
cannot express activation triggers, cannot bundle scripts, and gets concatenated into every prompt.
MCP prompts are "designed to be **user-controlled**, meaning they are exposed from servers to
clients with the intention of the user being able to explicitly select them for use" ([verified]
https://modelcontextprotocol.io/specification/2025-06-18/server/prompts), so an MCP server cannot
guarantee the skill ever reaches the model's context without a human typing a slash command. Neither
is a candidate for the canonical form. Both remain useful as *pointers* (section 5).

### The rule that keeps one source canonical

Write the frontmatter to the **spec field set only**. The spec defines exactly six fields
([verified] https://agentskills.io/specification):

| Field | Required | Constraint (verbatim from spec) |
| --- | --- | --- |
| `name` | Yes | "Max 64 characters. Lowercase letters, numbers, and hyphens only. Must not start or end with a hyphen." Also: "Must not contain consecutive hyphens", "Must match the parent directory name" |
| `description` | Yes | "Max 1024 characters. Non-empty. Describes what the skill does and when to use it." |
| `license` | No | "License name or reference to a bundled license file." |
| `compatibility` | No | "Max 500 characters. Indicates environment requirements (intended product, system packages, network access, etc.)." |
| `metadata` | No | "Arbitrary key-value mapping for additional metadata." A map from string keys to string values; "Clients can use this to store additional properties not defined by the Agent Skills spec" |
| `allowed-tools` | No | "Space-separated string of pre-approved tools the skill may use. (Experimental)" |

Claude Code accepts many further fields (`when_to_use`, `disable-model-invocation`,
`user-invocable`, `argument-hint`, `model`, `context`, `agent`, `hooks`, `paths`, `shell`, and others)
([unverified] reported from https://code.claude.com/docs/en/skills.md by a subagent; I confirmed the
open-standard framing and the location/precedence text on that page myself but did not enumerate the
extension fields). Cursor documents `paths`, `disable-model-invocation`, and `metadata` as its
optional set ([verified] https://cursor.com/docs/context/skills). **Using any host extension field is
the only real fork risk in this design** ([inference]): the file stays single, but its behavior
diverges silently on hosts that ignore the field. Keep extensions out of the canonical file.

### Required layout

The spec's directory structure, verbatim ([verified] https://agentskills.io/specification):

```
skill-name/
├── SKILL.md          # Required: metadata + instructions
├── scripts/          # Optional: executable code
├── references/       # Optional: documentation
├── assets/           # Optional: templates, resources
└── ...               # Any additional files or directories
```

File references: "When referencing other files in your skill, use relative paths from the skill
root" and "Keep file references one level deep from `SKILL.md`. Avoid deeply nested reference chains"
([verified] same URL).

Progressive disclosure budget, verbatim ([verified] same URL): metadata "(~100 tokens): The `name`
and `description` fields are loaded at startup for all skills"; instructions "(< 5000 tokens
recommended): The full `SKILL.md` body is loaded when the skill is activated"; resources "(as
needed)". Plus "Keep your main `SKILL.md` under 500 lines."

Host-side budgets are tighter than the spec's guidance and matter for the description, which is the
activation trigger:

- Claude Code: "each entry's combined text is capped at 1,536 characters regardless of budget"
  (combined `description` and `when_to_use`) ([verified] https://code.claude.com/docs/en/skills.md).
- Codex: the initial skill list is budgeted to "at most 2% of the model's context window, or 8,000
  characters" ([verified] https://learn.chatgpt.com/docs/build-skills).
- Cursor: no documented limit ([verified] absence on https://cursor.com/docs/context/skills).

[inference] Target a description under about 700 characters so it survives every host's truncation
with room to spare. The existing local skills in `~/.claude/skills/` push well past that, for example
`mira-workbench` at about 780 characters ([verified] `/Users/canepro/.claude/skills/mira-workbench/SKILL.md:3`,
measured at 794 bytes for the whole line including the `description: ` key), so this is a live
constraint, not a theoretical one.

A working reference implementation of the target shape is
`/Users/canepro/.claude/skills/mira-workbench/SKILL.md:1-6`: `name`, `description`, and
`metadata.short-description` only, with detail pushed into `references/operating-plan.md` and pulled
in by a body line that names the file and the condition for reading it ([verified], lines 22-23).
That is the pattern to copy. Note that this skill is Vincent's personal workbench and is **not** to
be an rc-repro dependency or an upstream contribution, per the map's out-of-scope list
(https://github.com/Canepro/rc-repro/issues/1) and `CONTEXT.md:55-60`. It is a format exemplar only.

## 2. Where the canonical skill should live in the rc-repro repo

**Recommendation: `rc_repro/data/skill/rc-repro/SKILL.md`, inside the Python package.**

The deciding constraint is the map's "installable by a user who just has rc-repro". The README's
recommended install is `pipx install git+https://github.com/klovekesh37/rc-repro` ([verified]
`README.md:55-59`). A pipx user has **no repository checkout**, so anything at a top-level path such
as `skills/` or `.agents/skills/` is invisible to them ([inference], but a direct consequence of how
pipx installs work). Package data, by contrast, ships in the wheel and lands next to the code.

The repository already uses exactly this pattern for its other shipped assets ([verified]
`pyproject.toml:28-29`):

```toml
[tool.setuptools.package-data]
rc_repro = ["data/*.yaml", "data/presets/*.yaml", "data/monitoring/*.json", "data/loadtest/*.js", "data/webui/*"]
```

so a skill directory is a fourth instance of an established convention, not a new mechanism.

[inference] Two implementation notes for whoever builds this:

- A new package-data pattern is needed. The existing entries are single-level globs; a skill with
  `references/` and `scripts/` needs recursive matching, e.g. `data/skill/**/*`. The build backend is
  pinned at `setuptools>=68` ([verified] `pyproject.toml:2`), which is recent enough that recursive
  globs should work, but **this needs an actual wheel-contents test before the design relies on it**.
  I did not build a wheel to confirm.
- `MANIFEST.in` currently contains only `recursive-include tests *.py` ([verified]), so sdist
  inclusion may need a line too.

### Repository-level adapters (committed, zero-install)

Alongside the canonical directory, commit two thin entry points so anyone working *inside* a checkout
gets the skill with no install step at all:

- `.agents/skills/rc-repro` -> `../../rc_repro/data/skill/rc-repro`
- `.claude/skills/rc-repro` -> `../../rc_repro/data/skill/rc-repro`

Those two paths cover all four hosts (section 5). Both Claude Code and Codex document symlink
support: "A `<skill-name>` entry in the enterprise, personal, or project locations can be a symlink to
a directory elsewhere on disk. Claude Code follows the symlink and reads `SKILL.md` from the target
directory, and if the same target is reachable from more than one location, Claude Code loads the
skill once" ([verified] https://code.claude.com/docs/en/skills.md), and "Codex supports symlinked
skill folders and follows the symlink target when scanning these locations" ([verified]
https://learn.chatgpt.com/docs/build-skills).

[inference] Upstream review risk: committing a vendor-named `.claude/` directory to an OSS Python
project invites an objection. `.agents/skills/` is the vendor-neutral path and is read by Codex,
Cursor, and Copilot. A defensible fallback is to commit only `.agents/skills/` and let
`rc-repro skill install` create the `.claude/skills/` entry on the user's machine.

## 3. What I verified about each host's discovery, in its own words

**Claude Code** ([verified] https://code.claude.com/docs/en/skills.md):

| Location | Path |
| --- | --- |
| Enterprise | See managed settings |
| Personal | `~/.claude/skills/<skill-name>/SKILL.md` |
| Project | `.claude/skills/<skill-name>/SKILL.md` |
| Plugin | `<plugin>/skills/<skill-name>/SKILL.md` |

Precedence, verbatim: "When skills share the same name across levels, enterprise overrides personal,
and personal overrides project." And: "Plugin skills use a `plugin-name:skill-name` namespace, so
they cannot conflict with other levels." Live reload: "Claude Code watches skill directories for file
changes... Claude Code picks up the change within the current session, without a restart."

**OpenAI Codex** ([verified] https://learn.chatgpt.com/docs/build-skills, cross-checked against a
local `codex-cli 0.145.0` install): read locations are `$CWD/.agents/skills`, `.agents/skills` in
parents up to the git root, `$REPO_ROOT/.agents/skills`, `$HOME/.agents/skills`, `/etc/codex/skills`,
and skills bundled with Codex. Duplicate handling, verbatim: "If two skills share the same `name`,
Codex doesn't merge them; both can appear in skill selectors." Codex also accepts an explicit
registration via config: `skills.config.<index>.path` is documented as "Path to a skill folder
containing `SKILL.md`", with `skills.config.<index>.enabled` as "Enable or disable the referenced
skill" ([verified] https://learn.chatgpt.com/docs/config-file/config-reference). Codex additionally
reads an optional `agents/openai.yaml` carrying `interface` (display_name, short_description, icons,
brand_color, default_prompt), `policy.allow_implicit_invocation`, and MCP `dependencies` ([verified]
https://learn.chatgpt.com/docs/build-skills). A live example of that file is
`/Users/canepro/.claude/skills/vincent-workflow/agents/openai.yaml` ([verified], 4 lines, `interface`
block only).

**Cursor** ([verified] https://cursor.com/docs/context/skills): project `.agents/skills/` and
`.cursor/skills/`, user `~/.agents/skills/` and `~/.cursor/skills/`. Compatibility statement,
verbatim: "For compatibility, Cursor also loads skills from Claude and Codex directories:
`.claude/skills/`, `.codex/skills/`, `~/.claude/skills/`, and `~/.codex/skills/`."

**GitHub Copilot** ([verified] https://docs.github.com/en/copilot/concepts/agents/about-agent-skills):
"Project skills, stored in your repository (`.github/skills`, `.claude/skills`, or `.agents/skills`)"
and "Personal skills, stored in your home directory and shared across projects (`~/.copilot/skills`
or `~/.agents/skills`)".

## 4. Version matching to an rc-repro release

rc-repro's version has a single source of truth: `version = "0.18.0"` in `pyproject.toml:7`, read at
runtime by `rc_repro/__init__.py:6-7` (`__version__ = metadata.version("rc-repro")`, falling back to
`"0.0.0-dev"` when the package is not installed) ([verified]).

**Blocker found: rc-repro has no CLI surface for its own version.** `grep -rn '__version__' rc_repro/`
returns only the two lines in `__init__.py` ([verified]), and the Typer app is constructed with no
version callback ([verified] `rc_repro/cli.py:29-33`). Worse, the obvious flag name is already taken:
`--version` / `-v` on `up` is the **Rocket.Chat** version ([verified] `rc_repro/cli.py:164`), and the
map explicitly preserves that meaning ("The existing `--version` remains the normal version input").
So version matching needs a new, differently-named surface. [inference] A machine-readable one, since
the map requires "stable rc-repro CLI/JSON contracts, never internal Python imports or
terminal-output scraping". The repository already has the `--json` idiom to copy
([verified] `rc_repro/cli.py:528`, `rc_repro/cli.py:1017`).

Recommended four-layer scheme, weakest binding to strongest:

1. **Stamp** the release into the canonical skill's frontmatter under the spec's `metadata` field,
   e.g. `metadata: { rc-repro-version: "0.18.0" }`. This is legal because `metadata` is "Arbitrary
   key-value mapping" of string values ([verified] https://agentskills.io/specification) and the spec
   even shows `version: "1.0"` inside `metadata` in its own example. Note carefully: the Agent Skills
   spec defines **no top-level `version` field** ([verified] by its absence from the frontmatter
   table), so `metadata` is the only standard-conformant place for it.
2. **Gate the release** with a test asserting the stamp equals `importlib.metadata.version("rc-repro")`.
   [inference] This is the piece that actually prevents drift; a stamp nobody checks will go stale on
   the first release that forgets it. The repository has a `tests/` suite and CI
   (`.github/workflows/ci.yml`) to hang it on ([verified] `git ls-files`).
3. **Preflight in the skill body**: make the skill's first instruction call the new version command
   and stop if the installed rc-repro disagrees with the stamp. [inference] This is the only layer
   that catches the real-world case, which is a *copied* skill left behind after an rc-repro upgrade.
   No host offers version negotiation, so the skill has to check itself.
4. **If distributed as a plugin**, set the same string in the plugin manifest. Claude Code "resolves
   a plugin's version from the first of these that is set: 1. `version` in the plugin's `plugin.json`
   2. `version` in the plugin's marketplace entry 3. The git commit SHA of the plugin's source", and
   warns "If `plugin.json` declares `"version": "1.0.0"`, pushing new commits without changing that
   string does nothing for existing users, because Claude Code sees the same version and keeps the
   cached copy. Bump the field on every release, or omit it to use the commit SHA" ([verified]
   https://code.claude.com/docs/en/plugin-marketplaces). Codex has a parallel mechanism with its own
   manifest at `.codex-plugin/plugin.json` carrying `name`, `version`, `description`, and `skills`
   ([verified] https://learn.chatgpt.com/docs/build-plugins), and the CLI exposes
   `codex plugin add|list|marketplace|remove` ([verified] `codex plugin --help` on codex-cli 0.145.0).

[inference] Do **not** make the plugin route the primary distribution. It doubles the manifests (one
per host family), adds a marketplace to host, and buys nothing the package-data route does not
already give, because rc-repro's own release already is the version boundary. Keep plugins as an
optional convenience for users who prefer `/plugin marketplace add`.

## 5. Per-host adapter table

Canonical body is one directory. "Adapter" below means the smallest artifact needed to make that host
see it.

| Host | Required entry point | Thin adapter needed | What it cannot express |
| --- | --- | --- | --- |
| Claude Code | `.claude/skills/<name>/SKILL.md` (project) or `~/.claude/skills/<name>/` (personal) [verified] | Symlink or copy of the canonical dir. Symlinks are documented and deduplicated across locations [verified] | Nothing missing; it is the superset host. Its extra fields are the fork risk, not a gap |
| OpenAI Codex | `.agents/skills/<name>/SKILL.md` at cwd, any parent up to git root, or `$HOME/.agents/skills` [verified] | Symlink or copy. Alternatively zero filesystem work: register `skills.config[].path` in `config.toml` [verified] | No `allowed-tools` equivalent. Closest control is `policy.allow_implicit_invocation` in `agents/openai.yaml`. No glob scoping [verified for the field set; the "no equivalent" reading is inference] |
| Cursor | `.cursor/skills/` or `.agents/skills/` [verified] | **None.** Cursor reads `.claude/skills/` and `.codex/skills/` for compatibility [verified] | No `allowed-tools`. Has `paths` and `disable-model-invocation`, so a superset in scoping and a subset in permissioning [verified field list] |
| GitHub Copilot | `.github/skills`, `.claude/skills`, or `.agents/skills` [verified] | **None**, if the repo already ships `.claude/skills/` or `.agents/skills/` [verified] | Glob scoping lives in `*.instructions.md`, not in skills [unverified] |
| Any host with `AGENTS.md` only | `AGENTS.md` at repo root, nested per directory, nearest wins [verified] | A few prose lines naming the canonical `SKILL.md` path and when to read it | Everything structural: no frontmatter at all ("the agent simply parses the text you provide" [verified]), no on-demand loading, no bundled scripts, no description-triggered activation. Codex truncates it at `project_doc_max_bytes` [verified key exists; the 32 KiB default is unverified] |
| Any MCP-capable host | No on-disk path. `prompts/list` + `prompts/get`, or `resources/*` | An MCP server returning the skill body or a `resource_link` | Cannot guarantee the host surfaces anything to the model. Prompts are "user-controlled" by design [verified], so no model-triggered activation |

[inference] The practical conclusion from this table: **two committed directories,
`.agents/skills/rc-repro/` and `.claude/skills/rc-repro/`, cover Claude Code, Codex, Cursor, and
Copilot with zero format translation.** The AGENTS.md and MCP rows are not adapters for the skill;
they are discovery hints for hosts that have no skill mechanism, and they should say "read this file"
rather than restate the skill, or the divergent-copy problem comes straight back.

## 6. How installation should work for a plain rc-repro user

The plain user is the pipx user with no checkout ([verified] `README.md:55-59`). Proposed contract,
all [inference]:

```
rc-repro skill install [--host claude|codex|cursor|copilot|all] [--scope user|project] [--link] [--json]
rc-repro skill status [--json]
rc-repro skill uninstall [--host ...] [--scope ...]
```

- `install` writes the packaged canonical directory into the host's documented location. Default is
  **copy**, not symlink: a symlink into `site-packages` breaks the moment a venv is rebuilt or
  `pipx reinstall` runs, and `pipx reinstall` is the README's recommended upgrade path ([verified]
  `README.md:91-98`). `--link` stays available for contributors working from a checkout, where the
  target is stable.
- The copy carries the version stamp from section 4, so `status` can compare stamp against installed
  rc-repro and report drift instead of failing mysteriously later.
- `--json` on both, to satisfy the map's stable-contract requirement.
- Default `--scope user` for `install`, since a pipx user typically is not standing in a repository.
- [inference] Wire revalidation into the existing `doctor` command (`rc_repro/cli.py:1606`) rather than
  inventing a second health surface. The map wants later runs to "silently revalidate the environment
  and not repeat settled questions", and `doctor` is already the README's post-install check
  ([verified] `README.md:70-75`).

For the checkout user, installation is nothing: the committed `.agents/skills/` and `.claude/skills/`
entries are picked up in place, and Claude Code even reloads them mid-session ([verified] live change
detection wording above).

## 7. Failure modes of the thin-adapter approach

1. **Personal silently beats project in Claude Code.** "enterprise overrides personal, and personal
   overrides project" ([verified] https://code.claude.com/docs/en/skills.md). A user who ran
   `rc-repro skill install --scope user` once, then upgrades rc-repro and works inside a fresh
   checkout, gets the **stale personal copy**, not the repo's current one. This is the single most
   likely real failure, and it is invisible without `skill status`. [inference]
2. **Duplicate visibility on Codex and Cursor.** Codex: "If two skills share the same `name`, Codex
   doesn't merge them; both can appear in skill selectors" ([verified]). Shipping both
   `.agents/skills/rc-repro/` and `.claude/skills/rc-repro/` means Cursor and Copilot can reach the
   same skill by two paths. Claude Code explicitly dedupes symlinked targets ([verified]); Codex,
   Cursor, and Copilot dedup behavior is **not documented** [verified by absence].
3. **Copy goes stale, symlink breaks.** There is no third option. Copy is safe against venv churn and
   unsafe against upgrades; symlink is the reverse. The version stamp plus `skill status` is what
   makes either survivable. [inference]
4. **Safety gates cannot be enforced by the host.** `allowed-tools` is flagged "Experimental. Support
   for this field may vary between agent implementations" ([verified]
   https://agentskills.io/specification), and Codex and Cursor document no equivalent field at all
   ([verified by absence]). Therefore the map's human gates (public exposure, unapproved clusters, new
   credentials, unowned deletion, unapproved retention) **must be enforced inside rc-repro's own CLI**,
   not declared in frontmatter. If they live only in the skill body, they are prose an agent may skip
   on any host. [inference, and the most consequential finding in this document]
5. **Host extension fields fork behavior without forking the file.** Adding
   `disable-model-invocation` makes the skill manual-only on Claude Code and Cursor and has no effect
   on Codex ([verified] field lists differ). One file, two behaviors, no diff to review. [inference]
6. **Description-budget crowding.** A user with 40 skills installed has each description shortened;
   Codex "shortened first when there are many skills" ([unverified] subagent report) and Claude Code
   caps at 1,536 characters ([verified]). A long trigger list can get cut precisely where the
   activation keywords live. [inference]
7. **No host does version negotiation.** Nothing stops a 0.18 skill from driving a 0.12 binary except
   the skill's own preflight. [inference]
8. **`.claude/` in an upstream OSS repo is a review-surface risk.** [inference] Not a technical
   failure, but it is the most likely reason this design gets pushed back upstream, and worth
   deciding before the PR.

## 8. What I could NOT determine

1. **Whether Cursor or Copilot follow symlinks** in any skill directory. Claude Code and Codex
   document it; Cursor's and GitHub's pages say nothing. Since the recommended repo adapters are
   symlinks, this needs an empirical test on both before the design is locked.
2. **Codex precedence across scopes.** Codex documents that duplicates both appear in selectors but
   states no precedence rule, so which body wins in-session is unknown.
3. **Whether `~/.codex/skills` is still a Codex read location.** The docs list only
   `$HOME/.agents/skills`, `/etc/codex/skills`, and the repo-scoped paths. This machine has
   `~/.codex/skills` populated with 66 entries and `~/.agents/skills -> ../.codex/skills` ([verified]
   by `ls -ld`), which would make it work via the documented path without Codex reading
   `~/.codex/skills` directly. I did not determine which is true.
4. **Whether recursive package-data globs (`data/skill/**/*`) actually land in the wheel** under the
   pinned `setuptools>=68`. I did not build a wheel.
5. **Codex marketplace file name and schema, and the source types `codex plugin marketplace add`
   accepts.** The CLI has the subcommand ([verified] `codex plugin --help`) but the docs page I
   fetched did not specify the marketplace format.
6. **Whether agentskills.io is normative or descriptive**, and who governs it. Claude Code, GitHub,
   and Cursor all link to it as "the open standard", and GitHub links to
   `github.com/agentskills/agentskills`, but I did not establish its governance or whether hosts are
   obliged to track it.
7. **Whether any host validates or surfaces `metadata`.** The spec says clients "can use this", which
   is permissive, not required. The version stamp is therefore agent-readable but host-unenforced, and
   layer 2 (the CI assertion) is what actually holds.
8. **The exact enterprise/managed skill path for Claude Code.** The docs table says only "See managed
   settings".
9. **Claude Code's full extension field list.** I confirmed the open-standard framing, the location
   table, precedence, symlinks, the 1,536-character cap, and live reload on
   https://code.claude.com/docs/en/skills.md myself. The enumeration of extension fields in section 1
   is a subagent report I did not independently re-read, hence [unverified].
10. **Whether Codex will actually act on a prose pointer in `AGENTS.md`.** No documented behavior
    either way, so the AGENTS.md row of the adapter table is a hope, not a contract.

## 9. Recommended decision for the map

[inference] Three sentences, if this becomes a "Decisions so far" entry:

- The canonical rc-repro agent skill is an Agent Skills `SKILL.md` directory using spec fields only,
  stored at `rc_repro/data/skill/rc-repro/` so it ships with every pip and pipx install.
- Host adapters are directory placements, never format translations: `.agents/skills/rc-repro/` and
  `.claude/skills/rc-repro/` committed for checkout users, and `rc-repro skill install` for everyone
  else.
- Version matching is a `metadata.rc-repro-version` stamp, a CI assertion against
  `pyproject.toml`'s version, and a skill-body preflight against a new JSON version command, because
  `--version` already means the Rocket.Chat version.
