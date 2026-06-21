#!/usr/bin/env python3
"""
judge — the comprehensive conformance scorecard (TEST_PLAN §4, the JUDGE).

Runs all three layers (S schema, F interface, B behaviour) against a daemon via
its adapter, then emits the pre-registered, lexicographic scorecard:
  1. GATE      — all HARD checks green (a hard FAIL ⇒ non-conformant)
  2. conformance % — decided checks that pass (BLOCKED excluded)
  3. simplicity    — daemon LOC + resolved-subcommand count + required config
  4. cold-start    — config-discovery modes supported (env + cwd-walk)
  5. extraction    — survived/adapted/rebuilt tag counts from EXTRACTION_TAGS.md

Self mode (one daemon): reports the scorecard + gate. Cross mode (two daemons)
ranks them lexicographically. Taste is excluded — every key is a count.

Usage: python3 judge.py [--daemon PATH] [--adapter DECL.json] [--home SYNC_HOME]
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _adapter          # noqa: E402
import _fixture          # noqa: E402
import test_behaviors    # noqa: E402
import test_interface    # noqa: E402
import test_schemas      # noqa: E402


def _all_checks(ad, home):
    res = []
    res += [(*r, "schema") for r in test_schemas.collect(home)]
    res += [(*r, "interface") for r in test_interface.collect(ad)]
    res += [(*r, "behaviour") for r in test_behaviors.collect(ad)]
    return res   # each: (id, inv, name, hard, status, layer)


def _repo_metrics(ad):
    daemon = ad.daemon
    loc = len(open(daemon).read().splitlines()) if os.path.exists(daemon) else None
    subcmds = sum(1 for c in _adapter.CANONICAL if ad.resolves(c))
    # cold-start: discovery modes the daemon supports (env var + cwd-walk)
    src = open(daemon).read() if os.path.exists(daemon) else ""
    modes = ("PARALLAX_HOME" in src) + ("partners.json" in src and "getcwd" in src)
    # extraction fidelity from the kernel log
    et = os.path.join(ROOT, "docs", "EXTRACTION_TAGS.md")
    tags = {}
    if os.path.exists(et):
        body = open(et).read()
        for t in ("survived", "adapted", "rebuilt", "stays"):
            tags[t] = len(re.findall(rf"\*\*{t}", body))
    return {"daemon_loc": loc, "subcommands_resolved": subcmds,
            "discovery_modes": modes, "extraction_tags": tags}


def scorecard(ad, home):
    checks = _all_checks(ad, home)
    decided = [c for c in checks if c[4] is not None]
    npass = sum(1 for c in decided if c[4])
    hard_fail = [c for c in checks if c[3] and c[4] is False]
    blocked = [c for c in checks if c[4] is None]
    return {"name": ad.name, "daemon": ad.daemon, "checks": checks,
            "gate": not hard_fail, "hard_fail": hard_fail, "blocked": blocked,
            "conformance": (npass, len(decided)), "metrics": _repo_metrics(ad)}


def _sym(s):
    return "BLOCKED" if s is None else ("PASS" if s else "FAIL")


def _print(sc):
    print(f"\n{'=' * 64}\nSCORECARD — {sc['name']}  ({sc['daemon']})\n{'=' * 64}")
    layer = None
    for cid, inv, name, hard, st, lyr in sc["checks"]:
        if lyr != layer:
            layer = lyr
            print(f"\n  [{lyr}]")
        print(f"    {_sym(st):7} {cid:5} {'(soft) ' if not hard else ''}{name}")
    p, d = sc["conformance"]
    m = sc["metrics"]
    print(f"\n  GATE (all hard checks green): {'PASS' if sc['gate'] else 'FAIL'}")
    if sc["hard_fail"]:
        for c in sc["hard_fail"]:
            print(f"      hard FAIL — {c[0]} {c[2]}")
    if sc["blocked"]:
        print(f"  BLOCKED (interface gaps → negotiate-and-log): "
              + ", ".join(c[0] for c in sc["blocked"]))
    print(f"  conformance: {p}/{d} decided checks pass")
    print(f"  simplicity:  daemon {m['daemon_loc']} LOC, {m['subcommands_resolved']}/5 subcommands")
    print(f"  cold-start:  {m['discovery_modes']} config-discovery mode(s)")
    print(f"  extraction:  {m['extraction_tags']}")


# lexicographic rank key (lower-is-better where noted); for the CROSS-run
def rank_key(sc):
    p, d = sc["conformance"]
    m = sc["metrics"]
    return (0 if sc["gate"] else 1,                       # gate first (0 wins)
            -(p / d if d else 0),                          # higher conformance wins
            m["daemon_loc"] or 1e9,                        # lower LOC wins
            -m["discovery_modes"],                         # more modes wins
            -sum(m["extraction_tags"].values()))           # more accounted tags wins


def main():
    daemon = sys.argv[sys.argv.index("--daemon") + 1] if "--daemon" in sys.argv else None
    ad = _adapter.from_declaration(sys.argv[sys.argv.index("--adapter") + 1], daemon) \
        if "--adapter" in sys.argv else _adapter.reference(daemon)
    home = sys.argv[sys.argv.index("--home") + 1] if "--home" in sys.argv else None
    cleanup = None
    if not home:                       # self-contained S1 on a throwaway fixture home
        cleanup = tempfile.mkdtemp()
        home, _, _ = _fixture.build(cleanup)
    sc = scorecard(ad, home)
    _print(sc)
    if cleanup:
        subprocess.run(["rm", "-rf", cleanup])
    # P3 — machine-readable verdict: pass/fail becomes a script gate, and verdicts
    # are diffable across rounds. The model never re-reads the prose scorecard.
    json.dump({"daemon": ad.name, "gate": sc["gate"], "conformance": list(sc["conformance"]),
               "blocked": [c[0] for c in sc["blocked"]],
               "per_check": {c[0]: ("PASS" if c[4] is True else "BLOCKED" if c[4] is None else "FAIL")
                             for c in sc["checks"]}},
              open(os.path.join(os.getcwd(), "_verdict.json"), "w"), indent=2)
    print(f"\n  VERDICT: {'CONFORMANT' if sc['gate'] else 'NON-CONFORMANT (hard fail)'}  "
          f"(machine-readable: _verdict.json)\n")
    return 0 if sc["gate"] else 1


if __name__ == "__main__":
    sys.exit(main())
