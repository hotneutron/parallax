# Codex CLI adapter

Codex uses native `AGENTS.md` discovery and the generic file-poll watcher
contract. Start `parallax.py watch <partner>` as a background task and inspect
`_inbox.json` on the next turn; Codex does not require a Parallax-specific
daemon integration.

`driver.py` is the explicit, platform-gated agent-guide smoke driver. It:

- creates disposable consumer and partner Git fixtures;
- copies the bundle's exact `AGENTS.md` into each synthetic consumer root so
  Codex discovers it natively;
- runs `codex exec --json` and normalizes command and edit events for
  `compat/run_agent_compat.py`;
- installs a `PreToolUse` guard that logs every supported tool call and denies
  direct synthetic-partner shell paths.

The driver uses Codex's `danger-full-access` sandbox only inside its temporary
fixture because a compatibility scenario must permit the agent to create a
reaction. It never supplies a real partner path, network remote, credential, or
push target. It requires explicit opt-in:

```sh
CODEX_AGENT_COMPAT_SMOKE=1 \
python3 compat/run_agent_compat.py \
  --profile codex-cli \
  --driver "$PWD/parallax/adapters/codex/driver.py"
```

The JSONL stream is the complete audit source; the hook is a guardrail, not the
sole audit mechanism. Codex documents native `AGENTS.md` discovery,
machine-readable `codex exec --json` events, and `PreToolUse` hooks in its
official documentation.
