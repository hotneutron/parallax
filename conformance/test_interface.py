#!/usr/bin/env python3
"""
Conformance — interface contract (TEST_PLAN §2 layer F; DAEMON_INTERFACE.md).

Asserts the INVOCATION contract a shared suite needs to drive any daemon:
config discovery (F1), canonical-subcommand resolution (F2), and the
machine-readable detect result shape (F3). Exit-code semantics (F4) are
behaviour effects, asserted in test_behaviors (B2/B6).

Usage: python3 test_interface.py [--daemon PATH] [--adapter DECL.json]
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _adapter
import _fixture
from _validate import validate

CHECKS = []


def check(cid, name, hard=True):
    def deco(fn):
        CHECKS.append((cid, name, hard, fn))
        return fn
    return deco


def _wrote_detect_for_p(ad, home):
    p = ad.detect_result_path(home)
    return os.path.exists(p) and json.load(open(p)).get("partner") == "p"


# ---- F1: config discovery (DAEMON_INTERFACE §1) — three regimes ----
@check("F1a", "config discovery: $PARALLAX_HOME honored from an unrelated cwd")
def f1a(ad, home, partner, ctx, tmp):
    elsewhere = os.path.join(tmp, "elsewhere")
    os.makedirs(elsewhere, exist_ok=True)
    ad.run(home, "detect", "p", cwd=elsewhere, env_home=True)
    return _wrote_detect_for_p(ad, home)


@check("F1b", "config discovery: nearest cwd-ancestor with partners.json (no env)")
def f1b(ad, home, partner, ctx, tmp):
    sub = os.path.join(home, "deep", "nested")
    os.makedirs(sub, exist_ok=True)
    if os.path.exists(ad.detect_result_path(home)):
        os.remove(ad.detect_result_path(home))
    ad.run(home, "detect", "p", cwd=sub, env_home=False)
    return _wrote_detect_for_p(ad, home)


@check("F1c", "config discovery is NOT script-relative (daemon lives outside home)")
def f1c(ad, home, partner, ctx, tmp):
    # the daemon script is in the repo's reference/, not in `home`; run from home
    # with no env → it must resolve `home` (via cwd), not its own script dir.
    if os.path.dirname(os.path.abspath(ad.daemon)).startswith(home):
        return None      # BLOCKED: can't prove not-script-relative if script IS in home
    if os.path.exists(ad.detect_result_path(home)):
        os.remove(ad.detect_result_path(home))
    ad.run(home, "detect", "p", cwd=home, env_home=False)
    return _wrote_detect_for_p(ad, home)


# ---- F2: canonical subcommands resolve ----
@check("F2", "all five canonical subcommands resolve in the adapter")
def f2(ad, home, partner, ctx, tmp):
    unresolved = [c for c in _adapter.CANONICAL if not ad.resolves(c)]
    return True if not unresolved else None     # naming gap → BLOCKED (interface layer)


# ---- F3: machine-readable detect result shape ----
@check("F3", "detect writes _detect.json matching the §4 shape")
def f3(ad, home, partner, ctx, tmp):
    ad.run(home, "detect", "p")
    p = ad.detect_result_path(home)
    if not os.path.exists(p):
        return False
    schema = json.load(open(os.path.join(HERE, "_detect_schema.json")))
    return not validate(json.load(open(p)), schema)


def collect(ad):
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        home, partner, ctx = _fixture.build(tmp)
        for cid, name, hard, fn in CHECKS:
            try:
                status = fn(ad, home, partner, ctx, tmp)
                status = None if status is None else bool(status)
            except KeyError as e:
                status, name = None, name + f"  [BLOCKED: subcommand {e} unresolved]"
            except Exception as e:
                status, name = False, name + f"  [error: {e}]"
            results.append((cid, "interface", name, hard, status))
    return results


def _sym(s):
    return "BLOCKED" if s is None else ("PASS" if s else "FAIL")


def main():
    daemon = sys.argv[sys.argv.index("--daemon") + 1] if "--daemon" in sys.argv else None
    ad = _adapter.from_declaration(sys.argv[sys.argv.index("--adapter") + 1], daemon) \
        if "--adapter" in sys.argv else _adapter.reference(daemon)
    print(f"parallax interface conformance — daemon: {ad.daemon}  (adapter: {ad.name})\n")
    results = collect(ad)
    for cid, _, name, hard, st in results:
        print(f"  {_sym(st):7} [{cid}{'' if hard else ' soft'}] {name}")
    hard_fail = [c for c in results if c[3] and c[4] is False]
    npass = sum(1 for *_, st in results if st is True)
    print(f"\n  {npass}/{len(results)} pass   hard failures: {len(hard_fail)}")
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
