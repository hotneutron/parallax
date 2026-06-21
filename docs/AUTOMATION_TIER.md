# The automation ladder — rungs 1–5

*Design/rationale backfill for parallax's automation tier: the ladder that takes the manual
rung-0 cycle (`EXCHANGE_MODEL.md`) toward hands-off operation **without** outrunning its own
safety enforcement. Each rung reuses rung 0's mechanisms unchanged and unlocks the next. v1
(backfill) — 2026-06-18.*

---

## 0. The ladder and its governing gate

```
  rung 0  the manual daemon cycle ............... EXCHANGE_MODEL.md
  rung 1  the watcher (event-driven detect) ..... §1 below
  rung 2  claims_index (claim-level diff) ..... SYNC_SURFACE.md
  rung 3  divergences (mirrored + diffed) ....... SYNC_SURFACE.md
  rung 4  auto-modal (contamination detector) ... §3 — parked (user buy-in)
  rung 5  L3 full autonomy + safety instruments . §4 — gated on 3 + 4
```

**The safety gate (P7).** Autonomy does **not** escalate past `detect`+`prepare` until embargo
redaction, round limits, the read-guard, and commit-before-relay are all live. A rung that
auto-relayed before those existed would be **auto-contamination**. Each rung unlocks the next;
do not skip to L3. This is why the ladder is sequenced, not dumped.

## 1. Rung 1 — the watcher (`watch`)

**What.** Block on the partner's local reflog (`.git/logs/HEAD`) until HEAD passes the pin, then
run the sanctioned `detect` (+ `prepare` on obligation), write `_inbox.json`, and **exit 0**.
It **never commits or relays** — the operator still owns the three sweeps and the decision.
Event-driven via `inotifywait`; `--poll <secs>` falls back where no file-watcher exists. Fires on
the partner's *reaction-commit or a time window*, never per-commit (noise).

**Why it stops at detect+prepare.** Per P7, hands-off *detection* is safe (it reads committed
state, logs to the manifest, redacts embargoes); hands-off *judgment* is not. The watcher
removes the polling toil, not the operator's verdict.

### The mechanism / adapter split (the load-bearing seam)
The watch **mechanism** (`parallax.py watch` + the `_inbox.json` / exit-0 contract) is
**harness-agnostic**. An **adapter** is thin, per-agent glue that wires that contract to one
coding agent's primitives — three hooks: **launch-bg** (run `watch` in the background),
**on-complete** (re-engage the agent when `_inbox.json` appears), **capture-prompt** (feed the
rung-4 prompt-log). Parallax ships a **superset** of adapters (`claude-code/`, `opencode/`,
`generic/`); a consumer selects its agent's. Adding one is additive — it changes no interface.

**Why the file/exit contract matters for conformance.** Because the seam is a *file + exit code*,
the mechanism is **conformance-tested directly** (B12/B12b/B12c — invoking `parallax.py` with no
agent CLI), so it binds *both teams' daemons* on any host. An adapter's glue can only be
exercised where its platform exists, so it runs as a **per-platform smoke test**, gated on the
platform, and **never claims conformance**. `generic/` adds no glue, so the mechanism contract
*is* its verification (B12 already covers it). *Conformance stops at the mechanism; the platform
layer is smoke-tested; neither claims to be the other.*

## 2. Rungs 2–3 — the findings/divergence diff surfaces

The claim-level read surface (`claims_index`, `index-diff`) and the divergence registry
(`divergences`, `div-diff`, `age-divergences`), plus the `detect → index-diff → read` funnel.
Full design in **`SYNC_SURFACE.md`**. These are *new reads*, so they inherit rung 0's
committed-only + manifest guarantees automatically (P1; conformance B13/B14).

## 3. Rung 4 — auto-modal (the user-channel contamination detector)

**What.** A **prompt-log** (hashed user prompts) on each side; the sync compares prompt-hashes,
and a convergence reached under the *same* prompt-hash is auto-tagged **modal** — a shared
trigger measures the prior, not the world (P3). This automates the modal judgment that is
currently manual, and closes the one contamination channel the gates can't filter: the
unfilterable human relay (P5).

**Why it's parked.** Logging user prompts is a privacy/consent boundary → it requires explicit
**user buy-in** before it ships. The shared *modal-tag convention* (same-hash ⟹ modal) follows
once the log exists. Until then, modal tagging stays manual.

## 4. Rung 5 — L3 full autonomy, with live safety instruments

**What.** (a) **modal auto-tagging** — extend rung 4 so convergences are tagged
independent/propagated/modal automatically from the prompt-log + read-manifest; (b) the
**divergence-rate alarm** — from rung 3, track divergences-per-sync and **alarm on a *falling*
rate** (a falling rate is a herding warning, not progress — P8). Only with **both** live may the
watcher escalate past detect+prepare to auto-relay *routine, non-substantive* acks.

**Why it's gated on 3 + 4.** The alarm needs the divergence registry (rung 3) as its data
source; auto-modal needs the prompt-log (rung 4). Autonomy without these instruments is flying
blind past the P7 gate — the protocol could herd (divergence collapsing) with nothing watching.
"Done" = the loop runs a zero-obligation or pure-ack cycle unattended **and** trips the alarm on
a synthetic herding run.
