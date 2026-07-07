#!/usr/bin/env python3
"""
Conformance — behaviour verification for ANY parallax daemon (TEST_PLAN §2 layer B).

Black-box: every assertion is an exit code, a file effect, or a subject-ABSENCE —
never the daemon's wording or its source. Point `--daemon` at a partner's
implementation (with its declared `--adapter`) and conformance is proven by
MEASUREMENT, so neither team reads the other's machinery (invariants I3/I1).

Tri-state per check: PASS / FAIL / BLOCKED (an interface gap — a canonical
subcommand the adapter can't resolve, or a declared-absent capability; routed to
negotiate-and-log, never scored as pass or fail).

Usage: python3 test_behaviors.py [--daemon PATH] [--adapter DECL.json]
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import _adapter
import _fixture
from _fixture import git, SECRET

CHECKS = []   # (id, inv, name, hard, fn)


def check(cid, inv, name, hard=True):
    def deco(fn):
        CHECKS.append((cid, inv, name, hard, fn))
        return fn
    return deco


def _detect_json(ad, home):
    p = ad.detect_result_path(home)
    return json.load(open(p)) if os.path.exists(p) else None


# ---- I3: reads are committed-only, logged, guarded ----
@check("B1", "I3", "read serves COMMITTED content (stdout), not the working tree")
def b1(ad, home, partner, ctx):
    # R2: content is delivered on stdout (diagnostics on stderr). Assert the
    # committed bytes are served and the dirtied working-tree bytes are not.
    r = ad.run(home, "read", "p", "docs/0003-stable.md")
    if r.returncode != 0:
        return False
    return "COMMITTED-BODY" in r.stdout and "DIRTY-BODY" not in r.stdout


@check("B2", "I3", "read of a path absent from HEAD is refused")
def b2(ad, home, partner, ctx):
    open(os.path.join(partner, "docs", "wip.md"), "w").write("uncommitted")   # untracked in partner
    r = ad.run(home, "read", "p", "docs/wip.md")
    return r.returncode != 0


@check("B3", "I8", "every successful read appends {ref, at} to the manifest")
def b3(ad, home, partner, ctx):
    mp = ad.manifest_path(home)
    n0 = len(json.load(open(mp)).get("reads", [])) if os.path.exists(mp) else 0
    ad.run(home, "read", "p", "docs/0002-reaction.md")
    if not os.path.exists(mp):
        return False
    reads = json.load(open(mp)).get("reads", [])
    return len(reads) >= n0 + 1 and any("0002-reaction.md" in r.get("ref", "") for r in reads) \
        and all("ref" in r and "at" in r for r in reads)


@check("B4", "I3", "read-guard blocks out-of-band partner access, allows in sync-mode")
def b4(ad, home, partner, ctx):
    if not ad.guard:
        return None                      # no guard declared → I3-enforcement gap (BLOCKED, soft)

    def g(ev):
        return subprocess.run([sys.executable, *ad.guard], input=json.dumps(ev),
                              capture_output=True, text=True,
                              env={**os.environ, "PARALLAX_HOME": home}).returncode
    flag = os.path.join(home, ad.sync_flag)
    if os.path.exists(flag):
        os.remove(flag)
    blocked = g({"tool_name": "Bash", "tool_input": {"command": f"cat {partner}/docs/0001.md"}}) == 2
    allowed = g({"tool_name": "Bash", "tool_input": {"command": "ls /home"}}) == 0
    open(flag, "w").write("on")
    sanctioned = g({"tool_name": "Bash", "tool_input": {"command": f"cat {partner}/docs/0001.md"}}) == 0
    os.remove(flag)
    return blocked and allowed and sanctioned


# ---- I4: commit-before-relay ----
@check("B5", "I4", "relay of a committed-clean path succeeds, output carries HEAD")
def b5(ad, home, partner, ctx):
    r = ad.run(home, "relay", "p", "clean.md")
    head = git(home, "rev-parse", "--short", "HEAD").strip()
    return r.returncode == 0 and head in r.stdout


@check("B6", "I4", "relay of an uncommitted/untracked path is refused")
def b6(ad, home, partner, ctx):
    return ad.run(home, "relay", "p", "dirty.md").returncode != 0


@check("B6c", "I4", "relay of a dirty repo-root path from a SUBDIRECTORY home is refused")
def b6c(ad, home, partner, ctx):
    # Consumer layout: PARALLAX_HOME is a subdirectory (methodology/cross_team) of the repo,
    # but the relayed path (dirty.md) is repo-root-relative. The gate must resolve it against
    # the repo ROOT — resolving against the subdir home silently matches nothing → false
    # "clean", leaking an uncommitted file. (home==repo-root masks this; op exposed it.)
    return ad.run(ctx["subhome"], "relay", "p", "dirty.md").returncode != 0


@check("B5b", "I4", "relay a clean path while ANOTHER file is dirty → succeeds (per-path scope)")
def b5b(ad, home, partner, ctx):
    # I4 scopes cleanliness to the RELAYED paths, not the whole tree. Commit a
    # second file, dirty it (tracked-modified, unrelated to clean.md), then relay
    # the still-clean clean.md — must succeed. A whole-tree-clean relay over-refuses
    # here; this names the per-path requirement explicitly (it is otherwise implicit
    # in the fixture's persistent untracked dirty.md).
    other = os.path.join(home, "other.md")
    open(other, "w").write("v1"); git(home, "add", "other.md"); git(home, "commit", "-qm", "other")
    open(other, "w").write("v2 dirty unrelated")
    r = ad.run(home, "relay", "p", "clean.md")
    head = git(home, "rev-parse", "--short", "HEAD").strip()
    return r.returncode == 0 and head in r.stdout


@check("B6d", "I4", "relay's _relay.json `from` is the repo name (root basename), not the sync-home basename (subdir-home; B6c class)", hard=False)
def b6d(ad, home, partner, ctx):
    # 4th B6c: `from` used basename(home()) — for a subdir home that's the home dir, not the repo root
    sub = ctx["subhome"]
    r = ad.run(sub, "relay", "p", "clean.md")
    rj = os.path.join(sub, "_relay.json")
    if r.returncode != 0 or not os.path.exists(rj):
        return False
    return json.load(open(rj)).get("from") == os.path.basename(home)


# ---- I5: embargo redaction ----
@check("B7", "I5", "detect redacts an embargoed commit subject")
def b7(ad, home, partner, ctx):
    out = (lambda r: r.stdout + r.stderr)(ad.run(home, "detect", "p"))
    return SECRET not in out and "GATE FAIL" not in out


@check("B8", "I5", "count never emits a commit subject")
def b8(ad, home, partner, ctx):
    out = (lambda r: r.stdout + r.stderr)(ad.run(home, "count", "p"))
    return SECRET not in out and "GATE FAIL" not in out and "verdict" not in out


@check("B7b", "I5", "detect redacts an active_until-only embargo (BOTH signals honored)")
def b7b(ad, home, partner, ctx):
    # The schema permits two activeness signals (active / active_until); a
    # conformant daemon honors BOTH (260613 schema pin). Rewrite the embargo to
    # active_until-only (no `active`), re-detect, then restore so order is moot.
    ep = os.path.join(home, "embargo_registry.json")
    saved = open(ep).read()
    json.dump({"embargoes": [{"topic_id": "E", "pattern": "GATE FAIL|corner",
                              "active_until": "2099-01-01"}]}, open(ep, "w"))
    out = (lambda r: r.stdout + r.stderr)(ad.run(home, "detect", "p"))
    open(ep, "w").write(saved)
    return SECRET not in out and "GATE FAIL" not in out


# ---- classify (config-driven; asserted on _detect.json, not wording) ----
@check("B9", "classify", "a reaction addressed to us → tier 1 (must-read)")
def b9(ad, home, partner, ctx):
    ad.run(home, "detect", "p")
    dj = _detect_json(ad, home)
    return dj is not None and any("0002-reaction.md" in p for p in dj["tiers"].get("1", []))


@check("B10", "classify", "a shared-contract (schema) change → obligation, not skipped")
def b10(ad, home, partner, ctx):
    ad.run(home, "detect", "p")
    dj = _detect_json(ad, home)
    if dj is None:
        return False
    in_obligation = any("schemas/" in p for p in dj["tiers"].get("2", []) + dj["tiers"].get("1", []))
    return in_obligation and dj["obligation"] is True


@check("B19", "classify", "an atypes doc lands at its CONFIGURED tier, not T1 (the D1 regression gate)", hard=False)
def b19(ad, home, partner, ctx):
    # the D1 bug (duplicate `if atype in atypes: return 1`) flipped every findings/brainstorm to T1
    _fixture.set_pin(home, "p", ctx["base"])
    ad.run(home, "detect", "p")
    dj = _detect_json(ad, home)
    if dj is None:
        return False
    t1, t2, t3 = dj["tiers"].get("1", []), dj["tiers"].get("2", []), dj["tiers"].get("3", [])
    findings_ok = any("0004-findings" in p for p in t2) and not any("0004-findings" in p for p in t1)
    brainstorm_ok = any("0005-brainstorm" in p for p in t3) and not any("0005-brainstorm" in p for p in t1)
    return findings_ok and brainstorm_ok


@check("B20", "classify", "topic-aligned brainstorm promotes T3→T2 with an auditable reason", hard=False)
def b20(ad, home, partner, ctx):
    # The fixture gives the reader a recent plan tagged bp1/iss/sim, and the
    # partner a brainstorm filename carrying bp1/iss/sim. `bp1` is configured as
    # a stop token, so promotion requires the substantive overlap {iss, sim}.
    _fixture.set_pin(home, "p", ctx["base"])
    ad.run(home, "detect", "p")
    dj = _detect_json(ad, home)
    if dj is None:
        return False
    promoted = any("0006-brainstorm-bp1-iss-sim" in p for p in dj["tiers"].get("2", []))
    not_t3 = not any("0006-brainstorm-bp1-iss-sim" in p for p in dj["tiers"].get("3", []))
    draft = json.load(open(os.path.join(home, "_sync_entry_draft.json")))
    reason = "\n".join(draft.get("to_review", []))
    return promoted and not_t3 and "topic-aligned" in reason and "iss" in reason and "sim" in reason


@check("B21", "classify/I3", "detect emits HEAD-readable rename destinations, not stale source paths")
def b21(ad, home, partner, ctx):
    _fixture.set_pin(home, "p", ctx["base"])
    ad.run(home, "detect", "p")
    dj = _detect_json(ad, home)
    if dj is None:
        return False
    surfaced = sum((dj["tiers"].get(str(t), []) for t in (1, 2, 3, 4)), [])
    has_new = any("docs/0007-plan-new.md" == p for p in surfaced)
    has_old = any("docs/0007-plan-old.md" == p for p in surfaced)
    read_new = ad.run(home, "read", "p", "docs/0007-plan-new.md").returncode == 0
    return has_new and not has_old and read_new


@check("B22", "detect", "an UNREACHABLE last_pinned is flagged + surfaces commits, never silent 'no new commits'")
def b22(ad, home, partner, ctx):
    # Bug #2: a pin that isn't a real commit (rebase/history-rewrite artifact) makes `git log <pin>..HEAD`
    # fail → git() swallows to [] → detect FALSELY reports "no new commits", masking every partner commit.
    _fixture.set_pin(home, "p", "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")  # 40-hex SHA absent from the repo
    r = ad.run(home, "detect", "p")
    if "no new commits" in r.stdout.lower():
        return False  # the buggy behaviour — silent masking
    # the fix must WARN that the pin is unreachable AND still surface the commits (never silently empty).
    warned = any(w in r.stdout.lower() for w in ("unreachable", "stale", "re-pin"))
    dj = _detect_json(ad, home)
    surfaced = dj is not None and any(dj["tiers"].get(str(t), []) for t in (1, 2, 3, 4))
    return warned and surfaced


# ---- I7: zero-obligation is inert ----
@check("B11", "I7", "zero-obligation sync → obligation:false AND no commit AND no pin-advance")
# ---- rung 0: addressed_to explicit field (reliable cross-team obligation signal) ----
@check("B18", "rung0", "addressed_to: <partner> field triggers T1, regardless of artifact_type", hard=False)
def b18(ad, home, partner, ctx):
    # Partner's docs/0002-reaction.md has addressed_to: consumer-repo — must be T1
    ad.run(home, "detect", "p")
    dj = _detect_json(ad, home)
    return dj is not None and any("0002-reaction.md" in p for p in dj["tiers"].get("1", []))

# ---- edge cases / crash-resistance continuation ----
def b11(ad, home, partner, ctx):
    _fixture.set_pin(home, "p", ctx["stable_c"])     # only the embargoed, non-triggered verdict is new
    head_before = git(home, "rev-parse", "HEAD").strip()
    pin_before = _fixture.get_pin(home, "p")
    ad.run(home, "detect", "p")
    dj = _detect_json(ad, home)
    head_after = git(home, "rev-parse", "HEAD").strip()
    pin_after = _fixture.get_pin(home, "p")
    return dj is not None and dj["obligation"] is False \
        and head_after == head_before and pin_after == pin_before


# ---- rung 2+3: index-diff / div-diff surface. Additive machinery, soft (BLOCKED if absent).
#      The daemon surface is measured (not the adapter — the mechanism contract). ----
@check("B13", "rung2/I8", "index-diff partner read appends {ref, at} to the manifest", hard=False)
def b13(ad, home, partner, ctx):
    manifest = os.path.join(home, "_parallax_read_log.json")
    before = json.load(open(manifest))["reads"] if os.path.exists(manifest) else []
    r = subprocess.run([ad.python, ad.daemon, "index-diff", "p"], cwd=home,
                       env={**os.environ, "PARALLAX_HOME": home},
                       capture_output=True, text=True, timeout=10)
    if r.returncode == 2 and "Unknown" in (r.stdout + r.stderr):
        return None
    after = json.load(open(manifest))["reads"] if os.path.exists(manifest) else []
    return len(after) > len(before)

@check("B13b", "rung2", "index-diff emits changed claim ids (JSON shape)", hard=False)
def b13b(ad, home, partner, ctx):
    r = subprocess.run([ad.python, ad.daemon, "index-diff", "p"], cwd=home,
                       env={**os.environ, "PARALLAX_HOME": home},
                       capture_output=True, text=True, timeout=10)
    if r.returncode == 2 and "Unknown" in (r.stdout + r.stderr):
        return None
    try:
        d = json.loads(r.stdout); return all(k in d for k in ("added", "removed", "changed"))
    except: return False

@check("B14", "rung3/I8", "div-diff partner read appends {ref, at} to the manifest", hard=False)
def b14(ad, home, partner, ctx):
    # seed local divergences.recent.json with one entry
    local = os.path.join(home, "divergences.recent.json")
    json.dump({"file": "recent", "entries": [
        {"claim": "c:LOCAL-1", "sides": {"ds4m": "L", "op": "R"}, "crux": "test",
         "status": "open", "last_updated": "2026-01-01"}
    ]}, open(local, "w"))
    manifest = os.path.join(home, "_parallax_read_log.json")
    before = len(json.load(open(manifest))["reads"]) if os.path.exists(manifest) else 0
    r = subprocess.run([ad.python, ad.daemon, "div-diff", "p"], cwd=home,
                       env={**os.environ, "PARALLAX_HOME": home},
                       capture_output=True, text=True, timeout=10)
    if r.returncode == 2 and "Unknown" in (r.stdout + r.stderr):
        return None
    after = len(json.load(open(manifest))["reads"]) if os.path.exists(manifest) else 0
    return after > before

@check("B14b", "rung3/F1", "div-diff is aging-robust (shared claim in recent vs archived → aging_mismatch)", hard=False)
def b14b(ad, home, partner, ctx):
    # Put the same claim in our recent but partner has it in archived.resolved
    local = os.path.join(home, "divergences.recent.json")
    json.dump({"file": "recent", "entries": [
        {"claim": "c:F-SHARED", "sides": {"ds4m": "shared-pos", "op": "shared-pos"},
         "crux": "aging test", "status": "open", "last_updated": "2026-01-01"}
    ]}, open(local, "w"))
    r = subprocess.run([ad.python, ad.daemon, "div-diff", "p"], cwd=home,
                       env={**os.environ, "PARALLAX_HOME": home},
                       capture_output=True, text=True, timeout=10)
    if r.returncode == 2 and "Unknown" in (r.stdout + r.stderr):
        return None
    try:
        d = json.loads(r.stdout)
        # c:F-SHARED must NOT be in only_theirs (it's present on both sides, just in different files)
        # It must appear in aging_mismatch with correct file labels
        shared_absent_from_only_theirs = "c:F-SHARED" not in d.get("only_theirs", [])
        aging = [a for a in d.get("aging_mismatch", []) if a["claim"] == "c:F-SHARED"]
        correct_mismatch = len(aging) == 1 and all(k in aging[0] for k in ("our_file", "their_file"))
        return shared_absent_from_only_theirs and correct_mismatch
    except: return False

@check("B15", "rung2", "detect suggests index-diff in `next` when claims_index.json changed (the funnel)", hard=False)
def b15(ad, home, partner, ctx):
    _fixture.set_pin(home, "p", ctx["base"])   # everything incl the rung-2/3 fixture commit is new
    ad.run(home, "detect", "p")
    dj = _detect_json(ad, home)
    return dj is not None and "index-diff p" in dj.get("next", [])

@check("B16", "rung3", "div-diff reads OUR divergences from the repo ROOT, not the sync home (subdir-home; B6c class)", hard=False)
def b16(ad, home, partner, ctx):
    # Consumer layout: PARALLAX_HOME is a subdirectory; our divergences live at the repo ROOT
    # (where the partner reads them via gitshow). A home-relative our-read misses them — the B6c
    # bug class in rung 3 (relay had the same home-vs-root bug). Run div-diff from the SUBDIR home;
    # it must still find the root-placed divergences.
    sub = ctx["subhome"]
    open(os.path.join(home, "divergences.recent.json"), "w").write(json.dumps({"file": "recent", "entries": [
        {"claim": "c:OURS-1", "sides": {"ds4m": "a", "op": "b"}, "crux": "x",
         "status": "open", "last_updated": "2026-01-01"}
    ]}))
    r = subprocess.run([ad.python, ad.daemon, "div-diff", "p"], cwd=sub,
                       env={**os.environ, "PARALLAX_HOME": sub}, capture_output=True, text=True, timeout=10)
    if r.returncode == 2 and "Unknown" in (r.stdout + r.stderr):
        return None
    try:
        d = json.loads(r.stdout)
        return "c:OURS-1" in d.get("only_ours", [])   # found OUR root-placed divergence from a subdir home
    except: return False
#      design — invokes the daemon directly, NO agent CLI / adapter involved; that is what makes
#      it conformance (a check that detected the env + drove an adapter would be a per-platform
#      integration test, not conformance — see adapters/README.md). The `generic` adapter adds no
#      glue, so this contract IS its verification; claude-code/opencode glue is smoke-tested per
#      platform, outside this suite. watch is additive machinery — soft, BLOCKED if the daemon
#      lacks it. ----
@check("B12", "rung1", "watch (poll mode) fires on HEAD-past-pin → _inbox.json + exit 0, never commits", hard=False)
def b12(ad, home, partner, ctx):
    # `--poll` forces the LOWEST-COMMON-DENOMINATOR path (no inotifywait → runs on any platform):
    # cross-platform conformance verifies the poll path first. Backlog (HEAD past pin) → fires now.
    _fixture.set_pin(home, "p", ctx["base"])         # pin behind HEAD → fires immediately
    h0 = git(home, "rev-parse", "HEAD").strip()      # the consumer (home) HEAD must not move
    try:
        r = subprocess.run([ad.python, ad.daemon, "watch", "p", "--poll", "1"], cwd=home,
                           env={**os.environ, "PARALLAX_HOME": home},
                           capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return False                                 # a watch that blocks past HEAD≠pin is a fail
    if r.returncode == 2 and "Unknown" in (r.stdout + r.stderr):
        return None                                  # watch not implemented → additive gap (BLOCKED)
    inbox = os.path.join(home, "_inbox.json")
    if r.returncode != 0 or not os.path.exists(inbox):
        return False
    ij = json.load(open(inbox))
    return bool(ij.get("their_head")) and git(home, "rev-parse", "HEAD").strip() == h0


def _watch_catches(ad, home, partner, extra, tag):
    # The watcher's real job: block while HEAD==pin, then WAKE on a fresh partner commit →
    # _inbox.json + exit 0. Shared by the poll path (B12b, cross-platform) and the inotify
    # fast-path (B12c, gated on the file-watcher). Proves the path works end-to-end.
    ph = git(partner, "rev-parse", "HEAD").strip()
    _fixture.set_pin(home, "p", ph)                  # pin == partner HEAD → watch blocks
    proc = subprocess.Popen([ad.python, ad.daemon, "watch", "p"] + extra, cwd=home,
                            env={**os.environ, "PARALLAX_HOME": home},
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    open(os.path.join(partner, "docs", f"wc-{tag}.md"), "w").write(
        "---\nartifact_type: reaction\nauthority: derived\nparent_artifacts: []\n---\n# n\n")
    git(partner, "add", "-A"); git(partner, "commit", "-qm", f"reaction: {tag} new commit")
    try:
        proc.communicate(timeout=12)                 # wakes within a poll interval of the commit
    except subprocess.TimeoutExpired:
        proc.kill(); return False
    return proc.returncode == 0 and os.path.exists(os.path.join(home, "_inbox.json"))


@check("B12b", "rung1", "watch (POLL path) blocks then CATCHES a new commit — cross-platform", hard=False)
def b12b(ad, home, partner, ctx):
    return _watch_catches(ad, home, partner, ["--poll", "0.3"], "poll")


@check("B12c", "rung1", "watch (INOTIFY fast-path) catches a new commit — where inotifywait exists", hard=False)
def b12c(ad, home, partner, ctx):
    if not shutil.which("inotifywait"):
        return None                                  # no file-watcher on this platform → BLOCKED; B12b (poll) covers it
    return _watch_catches(ad, home, partner, [], "inotify")   # no --poll → the inotify path


# ---- edge cases / crash-resistance: a robust daemon exits non-zero AND does not
#      traceback on bad invocation / missing / corrupt config. (Broad edge-case
#      coverage catches crash bugs a behaviour-only suite can miss.) ----

# ---- rung 2: convergence_audit (artifact-graph detector, ds4m-drafted) ----
@check("B17", "rung2", "convergence-audit flags conjectural evidence tagged independent", hard=False)
def b17(ad, home, partner, ctx):
    # Seed local claims_index with a conjectural+independent entry
    index = os.path.join(home, "claims_index.json")
    json.dump({"file": "recent", "entries": [
        {"id": "c:TEST-1", "statement": "test", "evidence_tier": "conjectural",
         "convergence_tag": "independent", "status": "open", "last_updated": "2026-01-01"}
    ]}, open(index, "w"))
    r = subprocess.run([ad.python, ad.daemon, "convergence-audit", "p"], cwd=home,
                       env={**os.environ, "PARALLAX_HOME": home},
                       capture_output=True, text=True, timeout=10)
    if r.returncode == 2 and "Unknown" in (r.stdout + r.stderr):
        return None
    try:
        d = json.loads(r.stdout)
        return any("conjectural" in r for f in d.get("flags", []) for r in f.get("reasons", []))
    except: return False

@check("B17b", "rung2/I8", "convergence-audit partner read is manifest-logged", hard=False)
def b17b(ad, home, partner, ctx):
    manifest = os.path.join(home, "_parallax_read_log.json")
    before = len(json.load(open(manifest))["reads"]) if os.path.exists(manifest) else 0
    subprocess.run([ad.python, ad.daemon, "convergence-audit", "p"], cwd=home,
                   env={**os.environ, "PARALLAX_HOME": home},
                   capture_output=True, text=True, timeout=10)
    after = len(json.load(open(manifest))["reads"]) if os.path.exists(manifest) else 0
    return after > before

@check("B17c", "rung2", "convergence-audit reads OUR claims from repo ROOT, not sync home (subdir-home; B6c class)", hard=False)
def b17c(ad, home, partner, ctx):
    # Like B16 for div-diff: place a flagged claim at repo ROOT, run from subdir home
    index = os.path.join(home, "claims_index.json")
    json.dump({"file": "recent", "entries": [
        {"id": "c:TEST-2", "statement": "test", "evidence_tier": "conjectural",
         "convergence_tag": "independent", "status": "open", "last_updated": "2026-01-01"}
    ]}, open(index, "w"))
    r = subprocess.run([ad.python, ad.daemon, "convergence-audit", "p"], cwd=ctx["subhome"],
                       env={**os.environ, "PARALLAX_HOME": ctx["subhome"]},
                       capture_output=True, text=True, timeout=10)
    if r.returncode == 2 and "Unknown" in (r.stdout + r.stderr):
        return None
    try:
        d = json.loads(r.stdout)
        return any("conjectural" in r for f in d.get("flags", []) for r in f.get("reasons", []))
    except: return False

def _raw(ad, home, *args, cwd=None):
    return subprocess.run([ad.python, ad.daemon, *args], cwd=cwd or home,
                          env={**os.environ, "PARALLAX_HOME": home}, capture_output=True, text=True)


def _graceful(r):
    return r.returncode != 0 and "Traceback (most recent call last)" not in r.stderr


# ---- Px: ledger subcommand ----
@check("P1", "interface", "ledger --recent 1 emits valid JSON summary matching sync_ledger.json head")
def p1(ad, home, partner, ctx):
    r = ad.run(home, "ledger", "--recent", "1")
    if r.returncode != 0:
        return False
    try:
        data = json.loads(r.stdout)
    except Exception:
        return False
    if not isinstance(data.get("total_entries"), int) or "shown" not in data:
        return False
    if not isinstance(data.get("entries"), list) or len(data["entries"]) == 0:
        return False
    entry = data["entries"][0]
    return entry.get("head") == ctx["base"]


@check("P2", "interface", "ledger --recent 3 returns at most 3 entries")
def p2(ad, home, partner, ctx):
    r = ad.run(home, "ledger", "--recent", "3")
    if r.returncode != 0:
        return False
    try:
        data = json.loads(r.stdout)
    except Exception:
        return False
    return data.get("shown", 999) <= 3


@check("E1", "robustness", "unknown command → non-zero, no traceback")
def e1(ad, home, partner, ctx):
    return _graceful(_raw(ad, home, "bogus-command", "p"))


@check("E2", "robustness", "missing required arg (read, no path) → non-zero, no traceback")
def e2(ad, home, partner, ctx):
    return _graceful(_raw(ad, home, "read", "p"))


@check("E3", "robustness", "unknown partner → non-zero, no traceback")
def e3(ad, home, partner, ctx):
    return _graceful(_raw(ad, home, "detect", "no-such-partner"))


@check("E4", "robustness", "missing partners.json → non-zero, no traceback")
def e4(ad, home, partner, ctx):
    empty = tempfile.mkdtemp()
    try:
        return _graceful(_raw(ad, empty, "detect", "p", cwd=empty))
    finally:
        subprocess.run(["rm", "-rf", empty])


@check("E5", "robustness", "corrupt partners.json → non-zero, no traceback")
def e5(ad, home, partner, ctx):
    bad = tempfile.mkdtemp()
    open(os.path.join(bad, "partners.json"), "w").write("{not valid json")
    try:
        return _graceful(_raw(ad, bad, "detect", "p", cwd=bad))
    finally:
        subprocess.run(["rm", "-rf", bad])


def collect(ad):
    """Run all checks on one throwaway fixture; return [(id, inv, name, hard, status)]
    with status in {True, False, None}."""
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        home, partner, ctx = _fixture.build(tmp)
        for cid, inv, name, hard, fn in CHECKS:
            try:
                status = fn(ad, home, partner, ctx)
                status = None if status is None else bool(status)
            except KeyError as e:
                status, name = None, name + f"  [BLOCKED: subcommand {e} unresolved]"
            except Exception as e:
                status, name = False, name + f"  [error: {e}]"
            results.append((cid, inv, name, hard, status))
    return results


def _sym(s):
    return "BLOCKED" if s is None else ("PASS" if s else "FAIL")


def main():
    daemon = sys.argv[sys.argv.index("--daemon") + 1] if "--daemon" in sys.argv else None
    ad = _adapter.from_declaration(sys.argv[sys.argv.index("--adapter") + 1], daemon) \
        if "--adapter" in sys.argv else _adapter.reference(daemon)
    print(f"parallax behaviour conformance — daemon: {ad.daemon}  (adapter: {ad.name})\n")
    results = collect(ad)
    for cid, inv, name, hard, st in results:
        print(f"  {_sym(st):7} [{cid}/{inv}{'' if hard else ' soft'}] {name}")
    npass = sum(1 for *_, st in results if st is True)
    hard_fail = [c for c in results if c[3] and c[4] is False]
    print(f"\n  {npass}/{len(results)} pass   hard failures: {len(hard_fail)}")
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
