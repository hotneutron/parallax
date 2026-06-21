# OpenCode adapter

OpenCode drives the watcher through the **generic file-poll** pattern (see
[`../generic`](../generic/README.md)) — it runs `parallax.py watch <partner>` as a background
shell process and the agent checks `_inbox.json` each turn. OpenCode has no Claude-Code-style
auto-re-invoke-on-background-exit, so it **polls the file** rather than relying on an exit
notification; the mechanism and the `_inbox.json` contract are unchanged.

## The three hooks

- **launch-bg** — OpenCode spawns `PARALLAX_HOME=<home> parallax.py watch <partner>` in the
  background (a backgrounded shell, or `--poll <secs>` under a system timer if no
  `inotifywait`).
- **on-complete** — the agent reads `<home>/_inbox.json` at the start of a turn; a new
  `their_head`/`at` ⇒ a drafted cycle to review (the sweeps + the decision; **never auto-commit
  or relay — §0**).
- **capture-prompt** *(rung 4, parked)* — via OpenCode's prompt/config hook if/when wired; else
  manual. Required user buy-in (logs prompts).

## Notes

Same mechanism, same contract as `claude-code`; only the surfacing differs (poll vs.
exit-notify). If OpenCode later exposes a background-completion signal, map **on-complete** to it
and this collapses to the claude-code shape — no mechanism change, since the file/exit contract
already covers both.
