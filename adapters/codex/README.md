# Codex CLI adapter

Codex uses native `AGENTS.md` discovery and the generic file-poll watcher
contract. Start `parallax.py watch <partner>` as a background task and inspect
`_inbox.json` on the next turn; Codex does not require a Parallax-specific
daemon integration.

The bundle's `compat/` directory owns the separate agent-guide compatibility
driver and audit tests. They are not Parallax mechanism or adapter code.
