# Parallax — Skill (the operating program)

> **Read this once.** It is the *judgment* layer — the calls a script cannot make
> (the three sweeps, governance, convergence accounting, the independence boundary).
> The routine cycle is **daemon-driven**: after this read you operate off the daemon's
> machine emissions (`_detect.json`, `_verdict.json`), not by re-reading prose.
>
> *What* the protocol is → `PROTOCOL.md`. *How to invoke* the daemon →
> `DAEMON_INTERFACE.md` / `.json`. *Hard rules* → `PROTOCOL_INVARIANTS.json`.
> This file is *how an agent operates it*.

## 1. Bootstrap (first contact)

Create a sync home; in it:
- `partners.json` — each partner's `{path, team_name, protocol_version, last_pinned}`
- `sync_ledger.json` → `{"entries": []}`; `embargo_registry.json` → `{"embargoes": []}`
- `tiers.json` (optional) — classification overrides for your domain (`config/tiers.example.json`)
- set `PARALLAX_HOME` to the sync home (or run from inside it).

Verify: `python3 parallax.py detect <partner>` resolves config and runs.

## 2. The sync cycle (machine-invokable — run, don't reason)

One cycle per exchange, one commit per cycle. The daemon emits the next actions; execute them.

1. `parallax.py detect <partner>` → writes `_detect.json`.
2. **Gate:** if `_detect.json.obligation == false` → zero-obligation: **report only, no
   commit, no pin advance** (the pin lags; the next substantive sync re-covers it for free).
3. Else **execute `_detect.json.next` in order** — it lists the exact `read <partner> <path>`
   commands (every tier-1 + tier-2 path) then `prepare <partner>`. `read` is the **sole**
   partner-read path (committed HEAD, logged to the manifest).
4. Apply judgment (§3–§5) to what you read; write one reaction doc.
5. `parallax.py prepare <partner> [--advance]` drafts the ledger entry; `--advance` advances
   the pin in-tree. **Advance the pin in this commit — never `--amend` after** (the partner's
   watcher may already have pinned it).
6. One commit. Then `parallax.py relay <partner> <paths>` to hand committed-clean paths across
   (commit-before-relay; cleanliness is per-path, not whole-tree).

Do **not** re-read this file mid-cycle — the daemon's JSON is the cycle state.

## 3. The three sweeps (before you act)

- **Grounding** — before building on a premise, trace it to a named artifact; verify a
  speculative source against a structured one first.
- **Generalization** — after a correction, re-verify every sibling claim from the same
  source; one error is evidence about the source, not just that claim.
- **Critique** — before issuing *or accepting* a correction, verify against the source's own
  namespace, at the right commit. Accepting a claim is the same operation as asserting one —
  verify first. (A cited reference that doesn't exist is the tell.)

## 4. Three-layer governance (when to compromise)

- **Findings — never.** Disagreement is signal; resolve by measurement only.
- **Machinery — diverge by design.** Converge only by independent adoption-on-merit; a shared
  codebase is a correlated error.
- **Interface — negotiate.** Measure → mechanical precedence (first-grounded name wins) →
  negotiate-and-log the residue. Reconcile only after both sides' results are committed.

## 5. Convergence accounting

Tag every cross-team corroboration: **independent** (reached without reading theirs — *cite the
forcing measurement*), **propagated** (adopted their framing — implementation only), **modal**
(explained by a shared prior/trigger — ~zero credit). **Pre-register**: commit your result
*before* reading theirs, so independence is auditable. Track divergences-per-sync — a falling
rate is a herding warning, not progress.

## 6. Severity · rounds · embargo · leak

- **Severity:** correction → same-day ack-or-fix; finding → batched into the cycle reaction;
  FYI / zero-obligation → report only.
- **Rounds:** no third prose round on a topic without a new measurement between (kills ping-pong).
- **Embargo:** while a pre-registration is in flight the daemon withholds matching commit
  subjects (including from `count`, which emits a numeric ahead-count, never subjects) — don't route around it.
- **Leak doctrine:** a leak is not a failure — an *undisclosed* one is. Disclose, downgrade the
  tag, continue. The goal is zero *unaccounted* leaks, not zero leaks.

## 7. Liveness & modes

Async-first: no step blocks on the partner. One-team → two-team is an upgrade path, never a
gate. A replacement session rebuilds the exchange state from committed artifacts alone — the
ledger *is* the manifest.

## 8. What this skill does NOT specify — the independence boundary

This file governs the **exchange**, never the **domain method**. How you solve the parallel
problem is your own, and **divergent by design**. A shared skill that drove the domain work
would correlate the two agents and collapse the independence the whole protocol exists to
protect. **Finding-level, non-negotiable.**

## 9. Interfaces

- `parallax.py` — the daemon (run it; `--read-guard` is the PreToolUse hook that blocks
  out-of-band partner access).
- `DAEMON_INTERFACE.md` / `.json` — the invocation contract (the `.json` is parseable: a script
  builds an adapter from it, no probing).
- `PROTOCOL.md` — the *what*; `PROTOCOL_INVARIANTS.json` — the hard rules (P1–P8).
- `schemas/` — the frozen interop contract (live data must validate); `conformance/` — verifies
  any daemon **by measurement**.

**Sign-off** is mutual audit: each side runs its suite against the daemon; ship when both are
green (`_verdict.json.gate == true` on each side). Disagreement between the two is signal —
resolve by measurement, never negotiation.
