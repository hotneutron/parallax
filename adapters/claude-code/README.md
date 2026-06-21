# Claude Code adapter

Wires the parallax automation **mechanism** (`parallax.py watch` + the file/exit contract) to
Claude Code's primitives. Claude Code runs the same `parallax.py` as any agent — this adapter
is just the three hooks, no mechanism code.

## The three hooks

- **launch-bg** — run `watch` as a background task. The agent runs
  `PARALLAX_HOME=<home> parallax.py watch <partner>` as a **`run_in_background`** Bash; it
  blocks on the partner's reflog (or `--poll <secs>`) and exits when there's a drafted cycle.
- **on-complete** — Claude Code **re-invokes the agent when a `run_in_background` task exits**.
  On re-invocation the agent reads `<home>/_inbox.json`
  (`{event, partner, their_head, obligation, draft, detect, at}`), reviews the drafted cycle
  (the grounding / generalization / critique sweeps + judgment), and decides. *The watcher
  never commits or relays — the agent owns that (§0).*
- **capture-prompt** *(rung 4, parked)* — a `UserPromptSubmit` hook appends a hashed prompt to
  `<home>/prompt_log.jsonl` for the modal detector. Deferred pending the user buy-in discussion.

## The loop

1. Agent launches `watch <partner>` (`run_in_background`).
2. Partner commits → the watcher fires `detect` (+ `prepare` on obligation), writes
   `_inbox.json` + the draft, and **exits 0**.
3. Claude Code re-invokes the agent on that exit.
4. Agent reads `_inbox.json`, runs the sweeps, decides, and — **manually**, per §0 — commits +
   relays the cycle.
5. Agent re-launches `watch` for the next cycle.

There is no persistent adapter *process*: this is the documented pattern plus the agent's
behavior. The mechanism's `_inbox.json` + exit-0 contract is exactly what lets Claude Code
(or any agent with "notify on background-task completion") drive it with no Claude-Code-
specific code in `parallax.py`. A poll-only agent reads `_inbox.json` instead of relying on
the exit notification — same contract.
