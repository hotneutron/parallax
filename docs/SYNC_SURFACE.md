# The claims sync surface — rungs 2–3, and how they compose with the base daemon

*Design/architecture note for the structured sync surface: `claims_index` (rung 2 — the
convergence-state surface) and the `divergences` registry (rung 3), and how `index-diff` /
`div-diff` / `age-divergences` compose with the base `detect` / `read` cycle. The contracts live
in `PROTOCOL.md` / `DAEMON_INTERFACE.md`; this doc is the **why** and the **how-they-fit**.
v1.1 — 2026-06-19 (reframed: convergence-state, not read-reduction; claims_index; generated from marks).*

---

## 1. What this surface is — the convergence-STATE surface (not a read-reducer)

A mis-framing to retire first (the one rung 2 was originally sold under): *"diff the index instead
of re-reading whole docs — the M1 read-reduction lever."* That's wrong — **`detect`/git already
give the changed-doc set since the pin** for free, so read-reduction is `detect`'s job, and a
diff of a curated index is a *worse* change-detector (blind to anything not in the index).

Rung 2's real purpose is **the convergence-STATE surface.** The protocol operates on **claims**
(corroborated / diverged / retired), not documents; `claims_index` makes claims first-class — each
carries its cross-team **`convergence_tag`** (independent / propagated / modal) + `status`.
`index-diff` reports the **state delta** (a claim went open→corroborated, or was retired) — *a
judgment git cannot parse* — which is what `prepare` turns into an auto-drafted ledger + P3
accounting (the brainstorm's "sync structured state, not prose"). Read-reduction is a *side effect*
of having a compact claim summary, not the point. Rung 3 makes **divergence** first-class the same
way: disagreement tracked to its resolving measurement.

The index is **compiled** from `claims:` marks in the source docs into a recent sliding window —
generated, not hand-authored, so it can't go stale. A claim enters when **offered into the
exchange** (corroboration or divergence subject, any doc type) and ages to `archived` (retained)
once settled. It is also **load-bearing for L3**: modal auto-tagging is the AND of three detectors
(read-manifest / `convergence_audit` / prompt-analyzer) written into `convergence_tag` — so this
surface is the recording substrate *and* one detector.

## 2. Three granularities (different lenses on "what changed since the pin")

| command | reads | granularity | logs to manifest (I8)? |
|---|---|---|---|
| `detect` | partner **commit log + changed-file list** | commit / **document** — which docs changed, their tier, is there an obligation | no — metadata, not file bodies |
| `index-diff` | partner **`claims_index.json`** (HEAD vs pin) | **claim** — `{added, removed, changed}` claim ids | **yes** — reads a file body via `_logged_gitshow` |
| `read` | one partner **file body** (HEAD) | full content → stdout + quarantine | yes |

All three are **pin-relative** and **committed-HEAD-only**. `read` is the only one that streams
*content* to the operator; `detect` and `index-diff` emit *structured summaries* of what moved.

## 3. The funnel (`detect` → `index-diff` → `read`)

`index-diff` does **not** replace `detect` or `read` — it sits between them, each step narrowing
the surface:

1. **`detect`** establishes that a cycle exists: *"3 commits since pin; `claims_index.json`
   changed, plus `docs/foo.md` (T1)."* It does not look inside the index.
2. **`index-diff`** zooms into the changed index: *"only `partner:F-SERVING-3` changed,
   `…-7` was added"* — 2 claims, not the whole 40-claim file.
3. **`read`** pulls just those claims' `evidence_ref`s — **targeted**, instead of re-reading the
   whole index or every changed doc.

**Worked example.** A cycle where `claims_index.json` + four docs changed: the base flow
`read`s ~5 docs to locate the moved claims; with the funnel you `index-diff` (one file) → learn
2 claim ids moved → `read` only those 2 evidence pointers. The surface drops from O(docs) to
O(changed-claims). That reduction *is* rung 2.

### Integration: `detect` suggests `index-diff`
`detect`'s machine-readable result carries a `next` list (the commands that discharge the
cycle). When `claims_index.json` is in the changed set, `detect` appends an `index-diff`
step to `next` **before** the per-doc `read`s — so a script (or agent) runs the funnel without
re-deriving it from prose. *(This wiring is shared machinery, so the change goes through the bilateral-review gate
before it lands on `main`.)*

## 4. The divergence registry (rung 3) — mirrored, diffed, aging-robust

Divergence is the signal of two independent teams; the registry makes it trackable. Design:

- **Mirrored + diffed.** Each team keeps its own `divergences.*.json`; `div-diff` diffs ours
  against the partner's committed copy. There is no single contended file — and a divergence the
  two teams *describe differently* is itself signal the diff surfaces.
- **Three-file aging** (`recent`, `archived.resolved`, `archived.open`) bounds the hot diff
  surface: only `recent` is the working set, but `div-diff` computes presence over
  **`recent ∪ archived.*` on both sides** so an aging-state mismatch never reads as a real
  divergence (the phantom-divergence trap). `aging_mismatch` reports those state differences
  *separately* from `disagree`.
- **`age-divergences`** is **local housekeeping** — it archives entries past the `aging`
  thresholds (days from `last_updated`); it reads no partner state. Thresholds live in the
  file's `aging` block so both sides age deterministically from the same inputs.
- **Closes only on measurement.** `status: resolved:*` is schema-gated to require a non-empty
  `resolution_measurement` — the "findings resolve by measurement only" rule is structural, not
  discipline. This file is the data source for L3's divergence-rate alarm (rung 5).

## 5. The axes the index touches (don't conflate them)

`claims_index` entries carry **two orthogonal axes**, plus a third that belongs to warrant:
- **`evidence_tier`** (`measured` / `inferred` / `conjectural`) — *how a claim is grounded*. A
  shared scale, deliberately non-overlapping with the authority terms (canonical in
  `artifact_types`, `evidence_axis`).
- **`convergence_tag`** (`independent` / `propagated` / `modal` / `n/a`) — *how a claim converged
  cross-team* (the restored axis, rung 2's real purpose). Distinct from `evidence_tier`: a claim can
  be `measured` yet `modal` (the dog-food case), or `conjectural` and never `independent` (the
  schema enforces `independent ⟹ measured/inferred`). The two together are why the index spans all
  doc types safely — `evidence_tier` marks a claim's *nature*, `convergence_tag` its *provenance*.
- the **authority axis** (`structured`/`derived`/`speculative`) is **warrant's**, applied to
  *documents*, not claims — namespace-relative per team. Don't confuse it with either index axis.

**Ref convention (token-efficient, consumer-defined).** `evidence_ref` (and the doc part of a
divergence's `resolution_measurement`) should be a **compact, repo-stable id**, not a full path
— the index exists to *shrink* the read surface, and verbose refs work against that. The exact
id format is the **consumer's** convention (parallax stays generic): a team whose docs follow a
unique-prefix naming scheme uses that prefix as the id; another team picks whatever short,
resolvable id its repo affords.

## 6. Current state (2026-06-19)

Both teams have authored instances; the surface ran against real cross-team data (the two sides measured ~14× and ~10× triage; `div-diff` aligned a divergence once coupled on a canonical id).
**In flight:** the `convergence_tag` restore (this schema, v1.1) and the `claims_index` rename
(v1.0→v1.1, a **bilateral lockstep** bump — both teams rename their instance at merge), plus
one team's **compiler** (generates the index from `claims:` marks) and the other's **`convergence_audit`**
(the artifact-graph modal detector). Rung 4 (the user-trigger detector) is designed but
build-deferred on a measured demand gate.
