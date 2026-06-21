# Parallax conformance — comprehensive test plan (the judge)

*Pre-registered judging spec for scoring **either** parallax daemon
(`reference/parallax.py` or a partner's) by black-box measurement. Frozen and
committed before any cross-run; a failed check names its cause and never moves
the bar. v0.2 — as-built 2026-06-17: the ★ matrix is implemented; self-conformance 31/31.*

> **Why pre-registered.** This file is the pre-registration. The same discipline
> that gates a pre-registered estimate (commit the gate before the verdict) gates the
> competition: the thresholds below are fixed *before* either daemon is scored, so
> neither candidate's results retro-fit the bar. The cross-run (this suite × a partner
> daemon) is run only after BOTH this plan and both daemons are committed
> (timing rule, I1).

---

## 0. The three agents this suite must be

From `test_behaviors.py`'s header, sharpened into testable duties:

1. **interop contract verifier** — both repos' live data validate the frozen schemas (I10), *both directions*.
2. **competition judge** — a pre-registered, lexicographic rubric (§4) turns measured conformance into a verdict.
3. **behaviour-match verifier** — verify a partner daemon by **measurement only**: assertions are exit codes, file effects, and subject-*absence* — never the daemon's wording or its source. This is what keeps the judge independence-preserving (I1/I3).

## 1. The adapter — what makes "either implementation" testable

The current suite calls canonical subcommand names directly. A partner daemon
whose CLI is `detect|prepare|read|status|check-relay` would then fail *every*
behaviour check on **naming**, not behaviour — conflating an interface mismatch
(negotiable, I6) with a real invariant violation. The comprehensive suite
inserts an **adapter** so the two are never confused:

```
adapter[daemon] = {
  subcommand: { detect→argv, read→argv, prepare→argv, relay→argv, count→argv },
  detect_result: path to the machine-readable detect file (DAEMON_INTERFACE §4),
  invoke: how to set cwd / env for config discovery,
}
```

- The alias map is derived from the daemon's **interface declaration** — its
  `--help` and its `DAEMON_INTERFACE.md` conformance — **never from reading its
  source** (that would break the independence the judge exists to protect).
- A check that fails *only* because no alias resolves a canonical subcommand is
  reported as an **INTERFACE gap (F-layer)**, routed to negotiate-and-log (I6),
  and the behaviour check is marked `BLOCKED`, not `FAIL`. A behaviour `FAIL`
  means: the interface resolved, the daemon ran, and the *effect* was wrong.
- Reference adapter (canonical) and the partner adapter both ship in the suite;
  the partner adapter is the instantiated interface contract, not a guess.

## 2. The check matrix

Hard = gates eligibility (a daemon failing any hard check is non-conformant,
regardless of style). Soft = audited proxy for a discipline invariant; scored,
not gated. **★ = added beyond the original 11-check suite — now built.**
**As-built (2026-06-17): 31/31 decided self-conformance, GATE PASS, VERDICT
CONFORMANT; S2 BLOCKED (cross-run only). S4 and F4 are not standalone checks —
see their rows.**

### Layer S — schema / interop contract (I10)

| id | check | hard? | measurement |
|---|---|---|---|
| S1 | consumer's live partners/ledger/embargo ⊨ frozen schemas | hard | `test_schemas` green |
| S2 ★ | **bidirectional** cross-validate: our-schema ⊨ partner-data **and** partner-schema ⊨ our-data | soft (cross-run) | both directions green — **BLOCKED in self-conformance** (needs both repos' live data; S3 proves the validation path) |
| S3 ★ | permissive-extras: a registry with foreign machinery fields (`beacon`, `our_head_msg`) **and** a registered-but-unsynced partner (`last_pinned: null`) validates | hard | validate green; this is the interop-minimum invariant |
| S4 ★ | `protocol_version` compatible across repos | soft | semver compat rule — *deferred* (no `protocol_version` divergence to gate yet) |

### Layer F — interface contract (DAEMON_INTERFACE.md)

| id | check | hard? | measurement |
|---|---|---|---|
| F1 ★ | config discovery: `$PARALLAX_HOME` honored; unset → nearest cwd-ancestor with `partners.json`; **not** script-relative (run daemon from a dir outside home, no env → still finds home) | hard | reads the right `partners.json` under 3 cwd/env regimes — **built as F1a/F1b/F1c** (one per regime) |
| F2 ★ | all five canonical subcommands resolve (direct or via adapter alias) | hard | adapter resolves each; else INTERFACE gap |
| F3 ★ | `detect` writes `_detect.json` matching the §4 shape `{partner,their_head,pinned,tiers:{1..4:[str]},obligation:bool}` | hard | validate against an embedded mini-schema |
| F4 | exit-code convention: read-uncommitted → non-zero; relay-dirty → non-zero; happy paths → zero | hard | **subsumed by B2/B6/E1–E5** — exit-code semantics are behaviour effects, not a standalone F-check |

### Layer B — behaviour / invariants (black-box, the heart)

| id | inv | check | hard? | measurement |
|---|---|---|---|---|
| B1 ★ | I3 | read serves **committed** content, not working-tree: commit docX, then dirty it in the partner tree; read returns the committed bytes | hard | read output == `git show HEAD:docX`, ≠ dirty bytes (replaces the near-vacuous c1) |
| B2 | I3 | read of a path absent from HEAD → non-zero, writes nothing | hard | c2, strengthened (assert no quarantine file written) |
| B3 ★ | I3/I8 | every successful read appends `{ref, at}` to the manifest (contamination boundary) | hard | manifest gained exactly one entry for the ref |
| B4 | I3 | read-guard blocks out-of-band partner access (off sync-mode), allows in sync-mode, allows unrelated | hard | guard_checks, generalized: a daemon **declaring no guard** registers an I3-enforcement gap (soft-flag), not a silent pass |
| B5 | I4 | relay of a committed-clean path → zero, output carries HEAD sha | hard | c3 |
| B6 | I4 | relay of a dirty/untracked path → non-zero | hard | c4 |
| B6c ★ | I4 | relay of a dirty **repo-root** path from a **subdirectory** home → non-zero | hard | the subdir-home false-clean bug: status must run from the repo toplevel, not the home dir |
| B5b ★ | I4 | relay a clean path while **another** file is dirty → zero (per-path scope) | hard | dirtiness is scoped to the relayed path, not the whole tree |
| B7 | I5 | detect redacts an embargoed commit subject | hard | c5 (SECRET absent from all output) |
| B7b ★ | I5 | detect redacts an `active_until`-only embargo (both signals honored) | hard | embargo without a `pre_registration_commit` still redacts |
| B8 | I5 | count emits `%h` only, never subjects | hard | c6 |
| B9 | classify | a reaction addressed to us → tier 1 (must-read) | hard | c7, on `_detect.json` |
| B10 ★ | classify | a **shared-contract change** (a `schemas/*` edit) → obligation, not skipped | hard | the bug this guards against; both implementations must surface it, asserted on `_detect.json.obligation` |
| B11 ★ | I7 | zero-obligation sync → **no commit, no pin-advance** | hard | c8 strengthened: assert `obligation:false` **and** repo HEAD unchanged **and** `last_pinned` unchanged |
| B12 ★ | rung1 | `watch` (poll mode) fires on HEAD-past-pin → writes `_inbox.json`, exits 0, **never commits** | soft | the automation-tier mechanism; platform-agnostic (`--poll`, no `inotifywait`) |
| B12b ★ | rung1 | `watch` (POLL path) blocks at HEAD==pin then **catches** a fresh partner commit — cross-platform | soft | end-to-end LCD: block → commit lands → `_inbox.json` written, exit 0 |
| B12c ★ | rung1 | `watch` (INOTIFY fast-path) catches a fresh commit — where `inotifywait` exists | soft | gated on `inotifywait`: **BLOCKED** on macOS/Windows (B12b covers them), PASS on Linux |

### Layer E — robustness (black-box, no traceback on bad input)

| id | check | hard? | measurement |
|---|---|---|---|
| E1 ★ | unknown command → non-zero, no traceback | hard | clean error, not a Python stack |
| E2 ★ | missing required arg (`read`, no path) → non-zero, no traceback | hard | clean error |
| E3 ★ | unknown partner → non-zero, no traceback | hard | clean error |
| E4 ★ | missing `partners.json` → non-zero, no traceback | hard | clean error |
| E5 ★ | corrupt `partners.json` → non-zero, no traceback | hard | clean error, not a JSON stack |

### Soft / discipline (audited, not runtime-gated)

| inv | proxy measured |
|---|---|
| I1 independence | timing-rule present in ledger entries (reconcile-after-both-committed); no uncommitted-read path exists (subsumed by B1–B4) |
| I2 convergence | `convergence:` field present + valued on reaction/cross_check docs; `independent` credits cite a measurement |
| I6 three-layer | divergence registry exists; each reconciled item logs its layer |
| I9 async | `beacon` field present; obligations carry on-miss intent; no step blocks on the partner |

## 3. Fixtures & harness

- **Throwaway sandbox per run** (as `build_fixture` already does): a synthetic
  partner repo (baseline → reaction-to-us → embargoed-verdict → committed-then-
  dirtied doc for B1) + a home repo (tiers/partners/ledger/embargo, a clean and
  a dirty file). Deterministic; never touches real repos.
- **Self-conformance first.** The suite must be green against this implementation's **own**
  daemon before it is allowed to judge a partner — a sound-instrument check. (This
  baseline today: **31/31** decided self-conformance; the ★ matrix is built.)
- **One sitting, published together.** Both candidates are scored in the same
  run; no tuning between seeing a result and re-scoring.

## 4. Scoring rubric (pre-registered, lexicographic)

A verdict compares candidates in this fixed order — earlier keys dominate:

1. **GATE — all hard checks green.** Any hard FAIL ⇒ non-conformant; ineligible
   to win on style. (A `BLOCKED` interface gap is resolved + re-run first, never
   scored as a pass or a fail.)
2. **Conformance %** — fraction of all checks (hard + soft proxies) green.
3. **Simplicity** — daemon LOC + subcommand count + config-file count; lower wins.
4. **Cold-start UX** — measured: commands + required env/config edits from a fresh
   clone to first successful `detect` (a scripted cold-start, counted).
5. **Extraction fidelity** — each `docs/EXTRACTION_TAGS.md` kernel element
   accounted (survived / adapted / rebuilt); higher auditable coverage wins.

**Taste is excluded.** Every key above is a count or a measured pass/fail.

## 5. Fairness protocol (the pre-registration contract)

- This plan + thresholds are committed **before** the first cross-run (the
  pre-registration act; timing rule, I1).
- Same fixture builder and same adapter contract for both daemons; adapter alias
  maps come from each daemon's interface declaration, **not** its source.
- Interface-naming failures ⇒ `BLOCKED` → negotiate-and-log (I6) → re-run; only
  resolved-interface-but-wrong-effect counts as a behaviour FAIL.
- Both results published together.

## 6. Sequencing — what gates the cross-run

| contract | state |
|---|---|
| schema seed | **frozen** at interop-minimum, bilateral by measurement (`1522`) — enables S1–S3 |
| daemon-interface seed | `DAEMON_INTERFACE.md` relayed; a partner's converging response is ready — **reconcile pending**; until done, F2 naming would dominate, so the cross-run is **blocked** on it |

**Until the interface reconcile lands:** run this comprehensive suite against this implementation's
**own** daemon (self-conformance — the §2 ★ matrix is now built, 31/31), proving
the instrument is sound. The partner cross-run starts the moment the interface
contract is frozen.

## 7. Build order (turning this plan into code)

**Status: complete (self-conformance 31/31; partner cross-run still gated on the interface reconcile, §6).** Steps 1–6 below are all built; later work added B5b/B6c/B7b (relay/embargo edge cases), the E-layer (robustness), and B12/B12b/B12c (rung-1 `watch`).

1. `_detect_schema.json` + F3 validator; wire `test_schemas` for S2/S3 (bidirectional + permissive-extras fixtures). ✓
2. Adapter module (`_adapter.py`): canonical→argv map, `--daemon` + `--adapter` flags; reference + partner adapters. ✓
3. Rewrite c1 → B1 (committed-vs-working-tree); add B3 (manifest), B10 (shared-contract obligation), B11 (no-commit assertion); generalize B4 guard. ✓
4. F1 config-discovery harness (3 cwd/env regimes → F1a/b/c). ✓
5. Rubric runner (`judge.py`): emits the lexicographic scorecard from the measured inputs + repo-scored simplicity/cold-start/extraction. ✓
6. Freeze (commit) → self-conformance green → await interface reconcile → cross-run. ✓ (self-conformance green; cross-run pending the reconcile)
