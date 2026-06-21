#!/usr/bin/env python3
"""
Throwaway git fixtures for the conformance suite. A synthetic partner repo and a
sync home, built fresh per run — deterministic, never touches a real repo.

Partner commit sequence (oldest→newest), each exercising a check:
  1  docs/0001.md                     baseline                      → `base`
  2  docs/0002-reaction.md            reaction addressed to us       (B9 tier-1)
  3  schemas/partners.schema.json     shared-contract change         (B10 obligation)  → `schema_c`
  4  docs/0003-stable.md "COMMITTED"  a committed doc                (B1)              → `stable_c`
  5  verdict.py  "GATE FAIL …"        embargoed, non-triggered HEAD  (B7/B8, B11)
After build, docs/0003-stable.md is OVERWRITTEN in the working tree with
"DIRTY-BODY" (uncommitted) so B1 can prove read serves the committed bytes.
"""
import json
import os
import subprocess

SECRET = "GATE FAIL corner-coincidence"   # an in-flight verdict that must never leak


def git(repo, *a):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True).stdout


def _init(repo):
    os.makedirs(repo, exist_ok=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@t.t")
    git(repo, "config", "user.name", "t")


def _w(repo, rel, body):
    p = os.path.join(repo, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(body)


def _commit(repo, msg):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg)
    return git(repo, "rev-parse", "--short", "HEAD").strip()


def build(tmp):
    partner, home = os.path.join(tmp, "partner"), os.path.join(tmp, "home")

    _init(partner)
    _w(partner, "docs/0001.md", "seed")
    base = _commit(partner, "seed: baseline")
    _w(partner, "docs/0002-reaction.md",
       "---\nartifact_type: reaction\naddressed_to: consumer-repo\nparent_artifacts:\n  - ../../consumer-repo/docs/x.md\n---\n# r\n")
    _commit(partner, "reaction: addressed to consumer-repo")
    _w(partner, "docs/0004-findings.md", "---\nartifact_type: findings\n---\n# f\n")
    _w(partner, "docs/0005-brainstorm.md", "---\nartifact_type: brainstorm\n---\n# b\n")
    _commit(partner, "docs: findings + brainstorm (atype-tier fixture)")
    _w(partner, "schemas/partners.schema.json", '{"type": "object"}')
    schema_c = _commit(partner, "fix: schema nullable last_pinned")
    _w(partner, "docs/0003-stable.md", "COMMITTED-BODY")
    stable_c = _commit(partner, "doc: stable")
    _w(partner, "verdict.py", "x")
    _commit(partner, f"feat: {SECRET} verdict")

    # Rung 2+3 fixture: claims_index + divergences (must commit BEFORE the dirty
    # overwrite — _commit uses git add -A and would stage the dirty file).
    _w(partner, "claims_index.json", json.dumps({"entries": [
        {"id": "c:F-1", "statement": "claim one", "evidence_tier": "measured",
         "evidence_ref": "docs/0001.md", "status": "open", "last_updated": "2026-01-01"}
    ]}))
    _w(partner, "divergences.recent.json", json.dumps({"file": "recent", "entries": [
        {"claim": "c:F-1", "sides": {"ds4m": "A", "op": "B"}, "crux": "measure it",
         "status": "open", "last_updated": "2026-01-01"}
    ]}))
    _w(partner, "divergences.archived.resolved.json", json.dumps({"file": "archived.resolved", "entries": [
        {"claim": "c:F-OLD", "sides": {"ds4m": "X", "op": "Y"}, "crux": "old",
         "resolution_measurement": "ran it", "status": "resolved:ds4m", "last_updated": "2020-01-01"},
        {"claim": "c:F-SHARED", "sides": {"ds4m": "shared-pos", "op": "shared-pos"},
         "crux": "aging test", "status": "open", "last_updated": "2026-01-01"}
    ]}))
    _commit(partner, "feat: claims_index + divergences (rung 2+3 fixture)")

    _w(partner, "docs/0003-stable.md", "DIRTY-BODY")          # uncommitted overwrite (B1)

    _init(home)
    json.dump({"self_name": "consumer-repo", "self_repo": "consumer-repo", "ledger_filename": "sync_ledger.json",
               "doc_prefix": "docs/", "addressed_to_us_types": ["reaction", "cross_check"],
               "type_tiers": {"findings": 2, "plan": 2, "brainstorm": 3, "reflection": 4},
               "ledger_tier": 2, "trigger_prefixes": ["docs/", "schemas/"],
               "trigger_files": ["sync_ledger.json"], "path_tier4_prefixes": [],
               "contract_prefixes": ["schemas/"], "contract_tier": 2},
              open(os.path.join(home, "tiers.json"), "w"))
    json.dump({"protocol_version": "0.1.0", "self": {"team_name": "c", "repo": "consumer-repo"},
               "partners": {"p": {"path": partner, "last_pinned": base}}},
              open(os.path.join(home, "partners.json"), "w"))
    json.dump({"embargoes": [{"topic_id": "E", "pattern": "GATE FAIL|corner", "active": True}]},
              open(os.path.join(home, "embargo_registry.json"), "w"))
    json.dump({"entries": [{"date": "2026-01-01", "their_head": base}]},
              open(os.path.join(home, "sync_ledger.json"), "w"))
    open(os.path.join(home, "clean.md"), "w").write("committed")
    git(home, "add", "-A")
    git(home, "commit", "-qm", "seed home")
    open(os.path.join(home, "dirty.md"), "w").write("uncommitted")    # untracked

    # Subdir-home layout: a consumer mounts the sync home as a SUBDIRECTORY of its repo
    # (e.g. methodology/cross_team). Relayed paths stay repo-root-relative, so the relay
    # gate must resolve them against the repo ROOT, not the (sub)home (B6c).
    subhome = os.path.join(home, "methodology", "cross_team")
    os.makedirs(subhome, exist_ok=True)
    for f in ("partners.json", "tiers.json", "embargo_registry.json", "sync_ledger.json"):
        json.dump(json.load(open(os.path.join(home, f))), open(os.path.join(subhome, f), "w"))

    return home, partner, {"base": base, "schema_c": schema_c, "stable_c": stable_c,
                           "subhome": subhome}


def set_pin(home, partner_name, sha):
    p = json.load(open(os.path.join(home, "partners.json")))
    p["partners"][partner_name]["last_pinned"] = sha
    json.dump(p, open(os.path.join(home, "partners.json"), "w"))


def get_pin(home, partner_name):
    return json.load(open(os.path.join(home, "partners.json")))["partners"][partner_name]["last_pinned"]
