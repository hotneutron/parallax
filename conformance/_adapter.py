#!/usr/bin/env python3
"""
Adapter — maps the canonical parallax subcommands (DAEMON_INTERFACE §2) to a
specific daemon's invocation, plus the daemon's declared read effects (where it
deposits quarantine, names its manifest, its sync-flag, its detect result).

This is what makes the suite test EITHER implementation without conflating an
interface mismatch with an invariant violation:
  - the alias map + effect names come from the daemon's INTERFACE DECLARATION
    (its --help / DAEMON_INTERFACE.md conformance), never from reading its source
    (that would break the independence the judge exists to protect);
  - a canonical subcommand with no resolving alias is an INTERFACE gap (the
    behaviour check returns BLOCKED, routed to negotiate-and-log, not FAIL).
"""
import json
import os
import subprocess
import sys

CANONICAL = ["detect", "read", "prepare", "relay", "count"]
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Adapter:
    def __init__(self, daemon, name="reference", aliases=None,
                 detect_result="_detect.json", quarantine="_parallax_quarantine",
                 manifest="_parallax_read_log.json", sync_flag=".parallax_sync_mode",
                 guard=None, python=None):
        self.daemon = os.path.abspath(daemon) if daemon else daemon
        self.name = name
        self.aliases = {**{c: [c] for c in CANONICAL}, **(aliases or {})}
        self.detect_result = detect_result
        self.quarantine = quarantine
        self.manifest = manifest
        self.sync_flag = sync_flag
        # guard: argv (after the python executable) for the PreToolUse read-guard
        # hook — e.g. [daemon, "--read-guard"] for the unified single-file daemon,
        # or [hook_file] for a standalone hook script. None ⇒ no guard declared.
        self.guard = guard
        self.python = python or sys.executable

    def resolves(self, canonical):
        return self.aliases.get(canonical) is not None

    def run(self, home, canonical, *args, cwd=None, env_home=True):
        """Invoke a canonical subcommand. env_home=False drops PARALLAX_HOME so
        config-discovery (F1) can be exercised by cwd alone."""
        if not self.resolves(canonical):
            raise KeyError(canonical)            # caller maps to BLOCKED
        argv = [self.python, self.daemon] + self.aliases[canonical] + list(args)
        env = {**os.environ}
        if env_home:
            env["PARALLAX_HOME"] = home
        else:
            env.pop("PARALLAX_HOME", None)
        return subprocess.run(argv, cwd=cwd or home, env=env,
                              capture_output=True, text=True)

    def detect_result_path(self, home):
        return os.path.join(home, self.detect_result)

    def quarantine_dir(self, home):
        return os.path.join(home, self.quarantine)

    def manifest_path(self, home):
        return os.path.join(home, self.manifest)


def reference(daemon=None):
    # the unified parallax tree ships the single-file daemon at ROOT/parallax.py
    # with the read-guard folded in as a `--read-guard` PreToolUse hook mode (2c).
    daemon = daemon or os.path.join(_ROOT, "parallax.py")
    return Adapter(daemon, "reference", guard=[daemon, "--read-guard"])


def from_declaration(path, daemon):
    """Partner adapter from a DECLARED interface file (a partner publishes this;
    the judge never reads partner source):
      {name, aliases:{canonical:[argv...]}, detect_result, quarantine, manifest,
       sync_flag, guard}."""
    d = json.load(open(path))
    g = d.get("guard")
    guard = [g] if isinstance(g, str) else g          # path → argv list
    return Adapter(daemon, d.get("name", "partner"), d.get("aliases"),
                   d.get("detect_result", "_detect.json"),
                   d.get("quarantine", "_parallax_quarantine"),
                   d.get("manifest", "_parallax_read_log.json"),
                   d.get("sync_flag", ".parallax_sync_mode"), guard)


def from_interface_declaration(path, daemon):
    """P5 — build an adapter by PARSING a partner's DAEMON_INTERFACE.json (the
    parseable invocation declaration), for INVOCATION: deterministic, zero `--help`
    parsing, zero behavioural probing, zero model tokens. The canonical→subcommand
    map is read from subcommands.<canonical>.argv[0]; effect filenames + detect
    result from the declaration. DISCIPLINE: parse-to-ACT only — the conformance
    VERDICT still measures (verify the claim), never trusts the declaration."""
    d = json.load(open(path))
    subs = d.get("subcommands", {})
    aliases = {c: [subs[c]["argv"][0]] for c in CANONICAL if c in subs and subs[c].get("argv")}
    eff, guard = d.get("effects", {}), d.get("guard", {})
    # guard: prefer the hook-mode invocation ([daemon, *invoke]); fall back to a
    # declared hook file. `invoke` is the daemon-relative argv (e.g. ["--read-guard"]).
    if isinstance(guard, dict) and guard.get("invoke"):
        guard_argv = [daemon, *guard["invoke"]]
    elif isinstance(guard, dict):
        guard_argv = [guard["file"]] if guard.get("file") else None
    else:
        guard_argv = [guard] if isinstance(guard, str) else guard
    return Adapter(daemon, (d.get("title", "partner").split("—")[0].strip() or "partner")[:24],
                   aliases,
                   d.get("detect_result", {}).get("file", "_detect.json"),
                   eff.get("quarantine", "_parallax_quarantine"),
                   eff.get("manifest", "_parallax_read_log.json"),
                   eff.get("sync_flag", ".parallax_sync_mode"),
                   guard_argv)
