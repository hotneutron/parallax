# adapters — the per-agent platform layer

The parallax **mechanism** (`parallax.py watch` + the `_inbox.json` / exit-0 contract) is
**harness-agnostic**. An adapter is the thin, **platform-specific** glue that wires that
contract to one coding agent's primitives — three hooks:

- **launch-bg** — run `watch` as a background task,
- **on-complete** — re-engage the agent when there's a drafted cycle (`_inbox.json`),
- **capture-prompt** — feed the prompt-log (rung 4).

Parallax ships a **superset** of adapters (`claude-code/`, `codex/`, `opencode/`, `generic/`); a consumer
selects its agent's. Adding one is additive — it changes no interface.

## Verification — and why an adapter is NOT "conformance"

The load-bearing distinction (the whole reason the mechanism uses a file/exit contract):

- **The mechanism is conformance-tested** — `conformance/` **B12**: *`watch` fires on
  HEAD-past-pin → writes `_inbox.json`, exits 0, never commits.* It invokes `parallax.py`
  **directly, with no agent CLI involved**, so it is **platform-agnostic** — which is exactly
  what lets it bind *both teams' daemons* to one contract on any host. A conformance check that
  *detected the environment and exercised a specific adapter* would no longer be conformance; it
  would be an integration test for one platform.
- **Adapters are verified by per-platform smoke tests.** An adapter's glue (does
  `run_in_background` actually re-invoke? does the prompt hook fire?) can only be exercised
  **where that platform exists**, so it runs as a smoke test alongside the adapter, **gated on
  the platform**, and **does not claim conformance**.
- **`generic/` is the special case:** it adds *no* platform glue — it just polls `_inbox.json`
  — so its verification *is* the mechanism contract. **B12 already covers it.** Only
  `claude-code/`/`codex/`/`opencode/` (real glue) need a per-platform smoke.

> Conformance stops at the mechanism (platform-agnostic, bilateral). The platform layer is
> smoke-tested per platform. Neither ever claims to be the other.
