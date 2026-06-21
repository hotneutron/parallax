# The exchange model — how the daemon enforces independence (rung 0)

*Design/rationale backfill for parallax's foundational layer: the sync cycle and the
independence enforcement underneath it. The **law** is `PROTOCOL.md` + `PROTOCOL_INVARIANTS.json`
(P1–P8); the **program** is `SKILL.md`; the **invocation** is `DAEMON_INTERFACE.md`. This doc is
the **why** — the threat model and how each mechanism answers it. v1 (backfill) — 2026-06-18.*

---

## 1. The threat the daemon defends against

Two teams cross-check by measurement; the **divergence** between independent views is the
signal (the parallax). The exchange channel that lets them compare is *also* the channel that
can destroy the thing it measures: if team A reads team B's in-progress work before committing
its own, A's "independent" result is now correlated with B's — a **silent contamination** that
inflates apparent agreement (you measure the shared influence, not the world). The daemon's job
is to let the exchange happen **without** eroding independence, and to make any contamination
that does occur **declared, not hidden** (P1, P5).

By-hand exchange is the contamination generator: someone greps the partner's working tree,
reads an uncommitted draft, forgets to log it. So the rule is **the exchange runs through the
daemon, never by hand** — the gates below are only reliable when mechanized.

## 2. The cycle

`detect → read → (the sweeps) → prepare → relay → one commit → pin advance`

| step | what | the guarantee it carries |
|---|---|---|
| `detect` | list partner commits since the pin, classify changed docs into tiers, surface obligations | reads commit metadata only; redacts embargoed subjects |
| `read` | the sanctioned partner read: `git show <committed-head>:<path>` → stdout + manifest | committed-only; every read logged (the boundary) |
| the **three sweeps** | grounding / generalization / critique — operator judgment | the daemon never decides; the human owns the verdict |
| `prepare` | draft the ledger entry + a one-per-cycle reaction stub | one reaction per cycle, one commit per cycle |
| `relay` | emit a pointer for committed-clean paths only | the partner only ever sees committed artifacts |
| **pin advance** | record `{date, their_head, reviewed, obligations}` in the ledger | the ledger *is* the manifest of record |

## 3. The five enforcement mechanisms (and the invariant each serves)

- **Committed-only reads (P1).** `read` and the diff surfaces `git show` the partner's *committed
  HEAD* — never the working tree. You physically cannot read their uncommitted, in-flight
  reasoning, so "commit your own result first" is enforced by what's *readable*, not by trust.
- **The read manifest (the boundary).** Every partner read appends `{ref, at}` to
  `_parallax_read_log.json`. This is the load-bearing guarantee: contamination is **accountable**
  — you can always say exactly what you read and when. *The manifest is the guarantee; everything
  else is defense-in-depth.* (Conformance B3; the diff surfaces honor it too — B13/B14.)
- **The read-guard (best-effort prevention).** A PreToolUse hook (`--read-guard`) blocks
  out-of-band partner access outside sanctioned-read mode. It is **fail-open by design** — it
  reduces accidents, but it is *not* the guarantee (the manifest is). Defense-in-depth, not a
  wall.
- **Commit-before-relay (P-relay gate).** `relay` refuses any path that isn't committed-clean, so
  a pointer can only ever carry committed content. The partner's daemon, reading committed HEAD,
  then *cannot* receive your working-tree wrinkles. Cleanliness is scoped **per relayed path**,
  not the whole tree. (Conformance B5/B6/B5b/B6c.)
- **Embargo redaction (P4 analogue).** While a pre-registration is in flight, matching commit
  subjects are withheld from `detect` and the (numeric-only) `count` — so an in-flight verdict
  cannot leak through the log before both sides commit. This is the pre-registration discipline
  applied to the channel. (Conformance B7/B7b/B8.)

## 4. The doctrines (the judgment layer the mechanisms can't cover)

- **The leak doctrine (P5).** A leak is not a failure — an *undisclosed* contamination is. The
  goal is **zero unaccounted leaks, not zero leaks**. The human relay channel is unfilterable;
  content it carries is covered by the doctrine (declare it, downgrade the credit to
  propagated/modal), not by any gate. The penalty for hiding a leak exceeds the penalty for
  declaring one.
- **Convergence accounting (P3).** Every corroboration is tagged **independent** (reached without
  reading the other's — must cite the forcing measurement), **propagated** (adopted their framing
  — corroborates implementation only), or **modal** (explained by a shared prior/trigger — ~zero
  credit). Same-family agents count as ~one evaluator for prior-driven claims.
- **Three-layer governance (P2).** *Findings* never compromise (resolve by measurement only);
  *machinery* diverges by design (a shared codebase is a correlated error); *interface* is
  negotiated (measure → mechanical precedence → negotiate-and-log).
- **Async-first (P6).** No step blocks on the partner; obligations carry `on_miss` intent; acks
  are never required, always sufficient. A quiet partner is a known state with a resume time, not
  a stall.

## 5. Why this composes upward

The base cycle is rung 0 of an automation ladder (`AUTOMATION_TIER.md`): every higher rung
(the watcher, the findings/divergence diff surfaces, auto-modal, full autonomy) reuses these
five mechanisms unchanged — e.g. `index-diff`/`div-diff` are new *reads*, so they inherit the
committed-only + manifest guarantees automatically. Autonomy is **gated** on these enforcements
being live (P7): a watcher that auto-relayed before embargo redaction + round limits existed
would be auto-contamination. The mechanisms are the foundation precisely because the ladder
stands on them.
