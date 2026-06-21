#!/usr/bin/env python3
"""
Conformance — schema / interop contract (TEST_PLAN §2 layer S; invariant I10;
also the SCHEMA-SEED tool).

S1  a repo's live ledger/partners/embargo validate against the frozen `schemas/`
    (needs a real SYNC_HOME; a partner runs this against THEIR live files —
    GREEN = the contract validates both repos' real artifacts by measurement).
S3  a synthetic registry carrying FOREIGN machinery extras (a per-partner beacon)
    AND a registered-but-unsynced partner (`last_pinned: null`) still validates —
    the interop-minimum / permissive-extras invariant (260613-1522). This is the
    code path the cross-run's bidirectional S2 exercises; tested here on a fixture
    so it runs without a partner.
S2  bidirectional cross-validate (op-schema ⊨ partner-data AND vice-versa) —
    activates at the CROSS-run (needs the partner's live data); reported N/A in
    self mode (the S3 fixture proves the mechanism).

Usage: python3 test_schemas.py [SYNC_HOME]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _validate import validate  # noqa: E402

SCHEMAS = os.path.join(os.path.dirname(HERE), "schemas")
PAIRS = [("sync_ledger.json", "ledger.schema.json"),
         ("partners.json", "partners.schema.json"),
         ("embargo_registry.json", "embargo.schema.json")]

# A registry that is interop-minimal in its REQUIRED fields but loaded with
# foreign machinery a partner daemon never reads (per-partner `beacon`,
# `our_head_msg`) and a registered-but-unsynced partner (null pin).
_PERMISSIVE_PARTNERS = {
    "protocol_version": "0.1.0",
    "self": {"team_name": "x", "repo": "x", "beacon": {"budget": "ok", "note": "foreign-extra"}},
    "partners": {
        "synced":   {"path": "/p/a", "last_pinned": "abc1234",
                     "beacon": {"budget": "low"}, "our_head_msg": "foreign machinery"},
        "unsynced": {"path": "/p/b", "last_pinned": None, "last_sync": None}
    }
}


def collect(home=None):
    """Return [(id, layer, name, hard, status)] with status in {True,False,None}."""
    out = []
    # S1 — live artifacts (only when a real home is given)
    if home:
        for data_f, schema_f in PAIRS:
            dp, sp = os.path.join(home, data_f), os.path.join(SCHEMAS, schema_f)
            if not os.path.exists(dp):
                continue
            errs = validate(json.load(open(dp)), json.load(open(sp)))
            out.append(("S1", "schema", f"live {data_f} ⊨ {schema_f}"
                        + (f"  [{errs[0]}]" if errs else ""), True, not errs))
    else:
        out.append(("S1", "schema", "live artifacts (pass a SYNC_HOME to run)", True, None))
    # S3 — permissive-extras / null-pin invariant (fixture; no home needed)
    schema = json.load(open(os.path.join(SCHEMAS, "partners.schema.json")))
    errs = validate(_PERMISSIVE_PARTNERS, schema)
    out.append(("S3", "schema", "registry with foreign extras + null last_pinned validates"
                + (f"  [{errs[0]}]" if errs else ""), True, not errs))
    # S5 — claims_index convergence_tag constraint: independent ⟹ measurement-based
    cschema = json.load(open(os.path.join(SCHEMAS, "claims_index.schema.json")))
    _good = {"entries": [{"id": "op:F-X-1", "statement": "s", "evidence_ref": "260101-0000",
                          "evidence_tier": "measured", "convergence_tag": "independent", "status": "corroborated"}]}
    _bad = {"entries": [{"id": "op:F-Y-1", "statement": "s",
                         "evidence_tier": "conjectural", "convergence_tag": "independent", "status": "open"}]}
    out.append(("S5", "schema", "claims_index: independent ⟹ measured/inferred (valid passes; conjectural+independent rejected)",
                True, (not validate(_good, cschema)) and bool(validate(_bad, cschema))))
    # S6 — divergences is team-agnostic: arbitrary team names (from partners.json) validate;
    # the schema fixes NO team names. Fails on the pre-genericization schema (required:[ds4m,op]).
    dschema = json.load(open(os.path.join(SCHEMAS, "divergences.schema.json")))
    _gen = {"entries": [{"claim": "c:X-1", "sides": {"alice": "A", "bob": "B"}, "crux": "measure it",
                         "status": "resolved:alice", "resolution_measurement": "ran the bench",
                         "last_updated": "2026-01-01"}]}
    _one = {"entries": [{"claim": "c:X-2", "sides": {"alice": "A"}, "crux": "q",
                         "status": "open", "last_updated": "2026-01-01"}]}
    out.append(("S6", "schema", "divergences: team-agnostic sides/status (arbitrary team names pass; <2 sides rejected)",
                True, (not validate(_gen, dschema)) and bool(validate(_one, dschema))))
    # S2 — bidirectional cross-validate: cross-run only
    out.append(("S2", "schema", "bidirectional cross-validate (cross-run only; S3 proves the path)",
                False, None))
    return out


def _sym(s):
    return "BLOCKED" if s is None else ("PASS" if s else "FAIL")


def main():
    home = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PARALLAX_HOME")
    print(f"parallax schema conformance — home: {home or '(none — S1 skipped)'}\n")
    results = collect(home)
    for cid, _, name, hard, st in results:
        print(f"  {_sym(st):7} [{cid}{'' if hard else ' soft'}] {name}")
    hard_fail = [c for c in results if c[3] and c[4] is False]
    npass = sum(1 for *_, st in results if st is True)
    print(f"\n  {npass}/{len(results)} pass   hard failures: {len(hard_fail)}")
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
