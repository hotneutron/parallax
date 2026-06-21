# The Parallax Protocol

> *Same axe, no parallax.*

**Parallax — measured disagreement.** A protocol for two (or more) independent
agents doing parallel work and reconciling by measurement, with independence
machine-enforced. Two sightlines on one target diverge; the angle of that
divergence is the measurement you cannot get from one eye. Collapse the
sightlines onto one line — no baseline — and the parallax is zero: no
information. So it is here. Independence is the asset; the *divergence* between
independent views is the signal; agreement without independence measures the
shared prior, not the world.

Version: see `VERSION`. Hard rules: `PROTOCOL_INVARIANTS.json`. Interop
contract: `schemas/`. This document states the *what*; a conformant
implementation supplies the *how* (`parallax.py` is one, forkable).

---

## 1. The model

Two agents work the same problem in separate repositories, independently. Each
commits its result. Only then do they reconcile — by reading each other's
*committed* artifacts through a daemon, comparing, and resolving differences by
measurement. Convergence reached independently corroborates; divergence is the
engine of discovery; neither is resolved by vote or seniority.

## 2. Convergence accounting

Every cross-agent corroboration claim is tagged:
- **independent** — reached without reading the other's; **must cite the
  measurement that forced the agreement**. Counts toward corroboration.
- **propagated** — adopted the other's framing. Corroborates implementation only.
- **modal** — explicable by a shared prior, textbook knowledge, or a shared
  trigger (including the human relay channel). ~zero credit: two readers of one
  textbook agreeing measures the prior. Same-family agents count as ~one
  evaluator for prior-driven claims.

Track divergences-per-sync; a falling rate is a herding warning, not progress.

## 3. Three-layer governance

- **Findings — never compromise.** Disagreement is signal; resolve by
  measurement only.
- **Machinery — divergence is the design.** Each agent's implementation may
  differ; converge only by independent adoption-on-merit. A shared codebase is
  a *correlated* error and is discouraged.
- **Interface — negotiate.** Shared conventions (schemas, names). Procedure, in
  order: (1) measure if measurable; (2) mechanical precedence if pure convention
  (first-grounded wins); (3) negotiate-and-log the residue.

**Timing rule:** reconcile only after both agents' independent results are
committed (the pre-registration analogue).

## 4. The three sweeps

- **Grounding** (before building on a premise): trace it to a named artifact;
  verify a speculative source against a structured one before acting.
- **Generalization** (after a correction): re-verify every sibling claim from
  the same source — one error is evidence about the source, not just the claim.
- **Critique** (before issuing OR accepting a correction): verify against the
  source's own namespace, at the right point in history. Accepting a claim is
  the same operation as issuing one — verify first. *(Verify a cited reference
  exists before inferring anything from it: a phantom citation is the tell.)*

## 5. Sync mechanics

The exchange runs through a daemon, never by hand; both repos are local, so it
uses `git -C`, never fetch.

- **read** — the primary partner-read path: `git show <committed-head>:<path>` into
  a transient quarantine, **logged to the manifest**. A working-tree-only path
  errors ("commit before relay"). A **read-guard** blocks every other access to
  the partner repo (load-bearing; fail-open — see I8). *(The diff surfaces below
  also read committed partner state — they likewise log to the manifest; "read" is
  the only path that streams content to the operator.)*
- **detect** — lists partner commits since the pin, applies a trigger filter,
  **redacts embargoed subjects**, and classifies each artifact into tiers
  (must-read addressed-to-us / should-read shared-contract / optional /
  never-read internal). The classifier is `type`-first.
- **relay** — emits a relay pointer only for committed-clean paths, carrying the
  HEAD (commit-before-relay, I4).
- **prepare** — auto-drafts the ledger entry + a one-per-cycle reaction stub.
- **watch** — blocks on the partner reflog until HEAD passes the pin, then runs
  `detect` (+ `prepare` on obligation) and writes `_inbox.json`; never commits/relays
  (the automation tier, rung 1).
- **index-diff / div-diff** — diff the partner's committed `claims_index` / `divergences`
  (the latter over recent ∪ archived, aging-robust) to shrink the read surface to changed
  claims; each partner read is manifest-logged (I8). **age-divergences** is local-only
  housekeeping (no partner read). (Rungs 2–3.)
- The **ledger** *is* the manifest: one entry per sync pinning
  `{date, their_head, reviewed, obligations}`.
- **Embargo** (`embargoes` registry): while a pre-registration is in flight,
  matching commit subjects are withheld — including from any partner-ahead
  count (a numeric ahead-count, never subjects) — so a verdict cannot leak through the log.

## 6. Conventions

One reaction doc per sync cycle; one commit per sync. **Severity:** correction =
same-day ack-or-fix; finding = batched into the cycle reaction; FYI /
zero-obligation = report only, no commit (the pin lags; the next substantive
sync re-covers it for free). **Round limit:** no third prose round on a topic
without a new measurement between. Acks are never required, always sufficient.

## 7. Liveness (async-first)

No step blocks on the partner. Obligations carry on-miss intent; one-team →
two-team is an upgrade path, never a gate. A committed liveness beacon makes a
quiet partner a known state with a resume time, not a stall. A replacement
session rebuilds the exchange state from committed artifacts alone.

## 8. The leak doctrine

A leak is not a failure — an *undisclosed contamination* is. The penalty for
hiding a leak exceeds the penalty for declaring one. The goal is **zero
unaccounted leaks, not zero leaks**: the manifest is the guarantee; the
read-guard is best-effort prevention. The human relay channel is unfilterable;
content it carries directly is covered by the doctrine, not the gate.

## 9. Versioning & compatibility

The protocol is versioned (`VERSION`, semver). `partners.json.protocol_version`
is checked for compatibility. The **schemas are the breaking-change surface**:
a schema change is a major bump and must be reconciled bilaterally before two
repos can sync. Implementations evolve freely (machinery).

---

*The protocol is subject to its own rules: amendments are pre-registered,
reconciled by measurement, version-bumped, and checked against the invariants.*
