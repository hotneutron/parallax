# parallax — measured disagreement

> *Same axe, no parallax.*

The cross-team **sync daemon** — and nothing lax about it. Two independent agents (teams) work
the same problem in separate repos and cross-check each other by **measurement**; the
independence that makes the cross-check meaningful is *machine-enforced*, not trusted.
"Parallax" is one object seen from two vantage points — the displacement between them is the
signal. **Same axe (same starting axiom), no parallax** (no displacement, no signal): the
divergence is the measurement you cannot get from one eye, so the protocol exists to keep the
two views genuinely independent.

A single script, `parallax.py`, runs the whole exchange between two **local** repos (it uses
`git -C`, never `fetch`).

## What it does

| subcommand | effect |
|---|---|
| `detect <partner>` | list the partner's commits since the last pin; classify each changed doc into tiers (T1 must-read → T4 never-read); surface triggered-but-unclassified files for manual review; draft a ledger entry. |
| `read <partner> <path>` | the **sole** sanctioned partner read — `git show`s the partner's *committed HEAD* to **stdout** and logs `{ref, at}` to the manifest. |
| `relay <partner> <path…>` | the **commit-before-relay** gate — refuses unless the paths are committed-clean, then emits a pointer carrying our HEAD. |
| `count <partner>` | partner-ahead commit count (no subjects — embargo-safe). |
| `prepare <partner>` | auto-draft the ledger entry + a one-per-cycle reaction stub. |
| `guard <path>` / `--read-guard` | the read-guard: blocks any access to a partner repo path outside a sanctioned read (`--read-guard` is the PreToolUse-hook mode). |
| `watch <partner> [--poll <secs>]` | block on the partner's reflog until HEAD passes the pin, then auto `detect` (+ `prepare` on obligation), write `_inbox.json`, exit 0 — **never commits/relays**. Event-driven via `inotifywait`; `--poll` falls back to polling. The automation tier's rung 1; the per-agent adapters live in `adapters/`. |

Independence is *enforced*: reads are committed-only + manifest-logged; the read-guard blocks
out-of-band partner access; embargo redaction withholds in-flight verdicts from `detect`/
`count`; and `relay` cannot point at uncommitted content. The contract is in **`PROTOCOL.md`**
+ **`PROTOCOL_INVARIANTS.json`**; the invocation surface in **`DAEMON_INTERFACE.md`**/`.json`;
the operating program (how an agent *runs* a cycle) in **`SKILL.md`**.

## Dependencies

Pure-stdlib Python 3 + `git` — nothing else for `detect`/`read`/`relay`/`count`/`prepare`/
`guard`. The **`watch`** fast-path additionally uses **`inotify-tools`** (`inotifywait`) for
event-driven watching of the partner's `.git/logs/HEAD`; without it, `watch` falls back to
polling (`--poll <secs>`, default 30s), so inotify-tools is **optional at runtime** — install
it on Linux (`apt install inotify-tools`) for the event-driven path, or rely on `--poll`
elsewhere (macOS/Windows). The conformance suite's inotify check (`B12c`) needs it too, and is
**BLOCKED** without it (the poll-path check `B12b` covers cross-platform conformance regardless).

## Configuration — a "sync home"

The daemon finds its config via `PARALLAX_HOME`, else the nearest cwd-ancestor with a
`partners.json` (so the home may sit at the repo root *or* in a subdirectory like
`methodology/cross_team/`). The home holds:

- **`partners.json`** — partner repos (path) + the `last_pinned` sync point.
- **`tiers.json`** — classification config (optional; built-in defaults otherwise): which
  `artifact_type`s map to which tier, `addressed_to_us` + `self_name` (a reaction is T1 only
  when a parent cites your repo), and the `trigger`/`contract` path sets.
- **`embargo_registry.json`** — in-flight pre-registrations whose subjects must be redacted.
- **`sync_ledger.json`** — one entry per exchange (the manifest of record).

## The role of `artifact_types`

`tiers.json` classifies partner work **by `artifact_type`** (`reaction → T1`, `findings →
T2`, …). Those type *names*, and each type's `default_tier`, are defined once in the shared
**[`artifact_types`](https://github.com/hotneutron/artifact_types)** registry — the single source of truth for the type
vocabulary. parallax's `tiers.json` is the per-team *instantiation* of those defaults (you can
override a tier locally); **warrant**'s `policy.json` instantiates the *same* types'
`default_authority`. Add a type once in the registry and both systems share it — no drift
between "what the daemon tiers" and "what the checker authorizes".

> The daemon is config-driven: it reads `tiers.json`, not the registry file, at runtime. The
> registry is the **naming authority** the config is written against, and is bundled as a
> submodule so the vocabulary travels with the repo.

## The three repos

| repo | governs | per-consumer config |
|---|---|---|
| **[artifact_types](https://github.com/hotneutron/artifact_types)** | the canonical type **vocabulary** — `{type → default_tier, default_authority}` | — (shared) |
| **parallax** (this) | the cross-team **exchange** (sync, independence enforcement) | `tiers.json` (type → tier) |
| **[warrant](https://github.com/hotneutron/warrant)** | each repo's internal **doc authority** (is a declared authority *warranted*?) | `policy.json` (type → authority) |

**Together.** A team's repo submodules **parallax** (to run the exchange) and **warrant** (to
validate its own `docs/`), and both draw their type vocabulary from **artifact_types**.
parallax governs what crosses *between* teams; warrant governs authority *within* a repo. They
share only the registry — by design, so the two cross-checking teams stay independent.

**Independently.** Each stands alone:
- **parallax** needs only a sync home (`partners.json` + optionally `tiers.json`) — no warrant,
  and no registry *file* at runtime (the type names in `tiers.json` suffice).
- **warrant** validates any repo's frontmatter from a `policy.json` alone; the registry
  drift-check runs only if the registry is present.
- **artifact_types** is a static JSON + schema — clone it for the vocabulary, nothing else.

## Verification

- **`conformance/`** — proves *any* daemon implementation by **measurement** (black-box: exit
  codes + file effects, never wording or source), via an adapter. The bilateral contract.
- **`spec-tests/`** — the daemon's own comprehensive self-test.

Each team may run its own daemon (machinery diverges by design); conformance is what binds the
two implementations to one spec. Reference governance: a shared `parallax.py` is the default,
opt out only on merit, and changes go proposal → independent review → bilateral agreement →
version bump.
