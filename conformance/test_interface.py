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
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
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


def _decl():
    path = os.path.join(ROOT, "DAEMON_INTERFACE.json")
    return json.load(open(path)) if os.path.exists(path) else None


def _template_path(home, template, partner):
    return os.path.join(home, template.replace("{partner}", partner))


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


@check("F4", "DAEMON_INTERFACE parse-driven detect resolves mirror + per-partner file")
def f4(ad, home, partner, ctx, tmp):
    decl = _decl()
    if not decl:
        return None
    iad = _adapter.from_interface_declaration(
        os.path.join(ROOT, "DAEMON_INTERFACE.json"), ad.daemon
    )
    r = iad.run(home, "detect", "p")
    if r.returncode != 0:
        return False
    detect = decl.get("detect_result", {})
    mirror = os.path.join(home, detect.get("file", ""))
    per_partner = _template_path(home, detect.get("per_partner_file", ""), "p")
    if not (os.path.exists(mirror) and os.path.exists(per_partner)):
        return False
    schema = json.load(open(os.path.join(HERE, "_detect_schema.json")))
    return (
        json.load(open(mirror)).get("partner") == "p"
        and json.load(open(per_partner)).get("partner") == "p"
        and not validate(json.load(open(mirror)), schema)
        and not validate(json.load(open(per_partner)), schema)
    )


@check("F5", "DAEMON_INTERFACE subcommands match daemon dispatch modulo extra machinery")
def f5(ad, home, partner, ctx, tmp):
    decl = _decl()
    if not decl or not ad.daemon or not os.path.exists(ad.daemon):
        return None
    declared = set(decl.get("subcommands", {}).keys())
    guard_argv = decl.get("guard", {}).get("cli_check", {}).get("argv", [])
    if guard_argv:
        declared.add(guard_argv[0])
    src = open(ad.daemon).read()
    dispatched = set(re.findall(r'(?:if|elif) c == "([^"]+)"', src))
    extra_machinery = {"convergence-audit"}
    return not (declared - dispatched) and not (dispatched - declared - extra_machinery)


@check("F6", "DAEMON_INTERFACE declares per-partner detect/draft/inbox scratch names")
def f6(ad, home, partner, ctx, tmp):
    decl = _decl()
    if not decl:
        return None
    detect = decl.get("detect_result", {})
    effects = decl.get("effects", {})
    required_templates = [
        detect.get("per_partner_file", ""),
        effects.get("entry_draft_per_partner", ""),
        effects.get("inbox_per_partner", ""),
    ]
    if not all("{partner}" in template for template in required_templates):
        return False
    r = ad.run(home, "detect", "p")
    if r.returncode != 0:
        return False
    expected_files = [
        detect.get("file", ""),
        detect.get("per_partner_file", "").replace("{partner}", "p"),
        effects.get("entry_draft", ""),
        effects.get("entry_draft_per_partner", "").replace("{partner}", "p"),
    ]
    return all(path and os.path.exists(os.path.join(home, path)) for path in expected_files)


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
