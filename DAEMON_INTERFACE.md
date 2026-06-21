# Parallax daemon interface — the invocation contract

The **schemas** freeze the *data*; this freezes the *invocation* — so a shared
conformance suite can verify any implementation **by measurement**, without
reading its code. Reconciled bilaterally (interface layer: measure → mechanical
precedence → negotiate-and-log). Version-tracked with `PROTOCOL.md`.

> This file is the **narrative**. Its machine-readable companion is
> **`DAEMON_INTERFACE.json`** — a structured, parseable invocation declaration
> (subcommand→argv, exit codes, effect filenames, detect-result + its validating
> schema). A consumer's adapter-builder *parses* it to invoke this daemon
> deterministically — no `--help` parsing, no behavioural probing, **no model
> tokens spent reasoning over prose** (the failure mode where an agent infers the
> invocation from prose and guesses wrong).

*Why this exists: when two independently-built daemons are cross-checked, they
diverge on config-location and subcommand names — the data schemas are necessary
but not sufficient. This is the second seed: the invocation surface a shared
conformance suite needs to drive either daemon.*

## 1. Config discovery

The daemon reads `partners.json` / the ledger / `embargo_registry.json` /
`tiers.json` from the **sync home**, resolved as:
`$PARALLAX_HOME` if set, **else the nearest ancestor of `cwd` containing
`partners.json`**, else the script directory. (Not script-relative *first* —
that breaks when the daemon is installed apart from its config.) Consumer repo
root = `git -C <home> rev-parse --show-toplevel`.

## 2. Subcommands (canonical names; aliases permitted if these resolve)

| command | effect |
|---|---|
| `detect <partner>` | list new partner commits, classify, write the result file (§4) |
| `read <partner> <path>` | read `partner@HEAD:path` into quarantine + manifest |
| `prepare <partner> [--advance]` | draft a ledger entry + a one-per-cycle reaction stub; `--advance` fills `reviewed` from the manifest and advances the pin |
| `relay <partner> <path…>` | emit a relay pointer for committed-clean paths |
| `count <partner>` | partner-ahead count (a numeric ahead-count, never subjects) |
| `guard <path>` | CLI check: is `<path>` inside a partner repo? (0 = no, 1 = yes) |
| `watch <partner> [--poll <secs>]` | block on the partner's reflog until HEAD passes the pin, then `detect` (+ `prepare` on obligation), write `_inbox.json`, exit 0 — **never commits/relays** (rung 1) |
| `index-diff <partner>` | diff the partner's committed `claims_index.json` against the last-pinned copy → `{added, removed, changed}` claim ids for targeted reads; partner reads append to the read-log (I8) (rung 2) |
| `div-diff <partner>` | diff our `divergences.*` against the partner's over **recent ∪ archived** (aging-robust) → `{only_ours, only_theirs, disagree, aging_mismatch}`; partner reads append to the read-log (I8) (rung 3) |
| `age-divergences` | local housekeeping: archive resolved/open entries past the `aging` thresholds (days from `last_updated`) into `divergences.archived.*.json` — no partner read (rung 3) |

The **read-guard** is the same single file invoked as a PreToolUse hook:
`parallax.py --read-guard` reads a tool-call event as JSON on stdin and blocks
out-of-band partner access (exit 2 denies the tool call; the sync-flag file is
the sanctioned-access escape hatch). One file, automatic enforcement.

## 3. Exit codes (the convention-independent assertions)

- `0` — success / allowed.
- **non-zero** — refused / blocked. **Required** for: `read` of a path not in
  the partner's committed HEAD (commit-before-relay); `relay` of a dirty/untracked
  **relayed path**; an unknown partner; a missing/corrupt config. Cleanliness is
  scoped **per-path** (the paths named to `relay`), **not** the whole working
  tree — an unrelated dirty/untracked file does NOT block relaying a clean path.

## 4. Machine-readable detect result

`detect` writes `<home>/_detect.json` so the suite asserts on structure, not
wording:

```json
{ "partner": "...", "their_head": "...", "pinned": "...",
  "tiers": {"1": ["path", ...], "2": [...], "3": [...], "4": [...]},
  "obligation": true,
  "next": ["read <partner> <path>", "...", "prepare <partner>"] }
```

`obligation` = (tier 1 or tier 2 non-empty). `next` lists a `read` command for
**every** tier-1 and tier-2 path, then `prepare` iff there is an obligation — so
a script can discharge the cycle without re-reading prose. The conformance suite
keys its classify / zero-obligation checks on this file, never on stdout strings.
`_detect.json` validates against `conformance/_detect_schema.json`.

## 5. read / relay effects

- `read` (committed): **streams the content to stdout** and appends `{ref, at}`
  to the read-log; diagnostics to stderr; exit 0. The read-log is the I8
  contamination boundary, separable from delivery.
- `index-diff` / `div-diff`: each partner read of a committed file (`claims_index.json`,
  `divergences.*.json`) **also appends `{ref, at}` to the read-log** — the same I8 boundary
  applies to the diff surfaces, not just `read`.
- `read` (uncommitted / not in HEAD): exit non-zero, emits no content.
- `relay` (a clean relayed path): exit 0; output includes the HEAD sha. Other
  files' dirty/untracked state is irrelevant — scope is per-path (I4).
- `relay` (a dirty/untracked relayed path): exit non-zero.

## 6. Embargo (already schema-frozen)

`detect` and `count` redact commit subjects matching an active embargo pattern;
`count` emits a numeric ahead-count, never subjects.

---

Implementations diverge freely **below** this surface — language, decomposition,
internal names, extra commands — that is machinery. This contract is the
**minimum a shared conformance suite needs**; nothing more is frozen.
