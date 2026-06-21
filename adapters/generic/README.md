# Generic adapter (file-poll)

The lowest-common-denominator adapter — for any agent or environment **without** a native
"notify me when a background task finishes" signal. It relies only on the mechanism's universal
contract: the watcher **writes `_inbox.json` and exits 0** when there's a drafted cycle, so the
inbox *file* is the channel and exit-notification is merely a convenience some agents add.

## The three hooks

- **launch-bg** — run the watcher detached, however the environment allows:
  - a shell the agent can background: `PARALLAX_HOME=<home> parallax.py watch <partner> &`
  - a system timer (no file-watcher needed): `parallax.py watch <partner> --poll <secs>` under
    cron / systemd / a loop — poll mode re-checks the partner HEAD on the interval.
  - a separate terminal / tmux pane running `watch`.
- **on-complete / poll** — with no exit-notification, **check `_inbox.json` at the start of each
  turn**. It carries `{event, partner, their_head, obligation, draft, detect, at}`; a fresh
  `their_head`/`at` ⇒ a drafted cycle to review. Process it (the sweeps + the decision). *The
  watcher never commits or relays — that stays manual (§0).* (If the launcher can react to the
  watcher's exit, re-run it then; otherwise the file poll is sufficient.)
- **capture-prompt** *(rung 4, parked)* — append a hashed prompt to `prompt_log.jsonl` via
  whatever prompt hook the environment offers; manual if none.

## When to use

Any agent without Claude Code's auto-re-invoke-on-background-exit — OpenCode, aider, a bare
terminal, cron/systemd. The mechanism is identical across all of them; only *how the operator
is reached* differs, and `_inbox.json` is the part every environment can read.
