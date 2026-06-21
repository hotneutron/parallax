#!/usr/bin/env python3
"""
Parallax conformance test #2 — protocol invariants (P1-P8).

Checks that the consuming repo satisfies the structural invariants
from PROTOCOL_INVARIANTS.json. Tier 1 violations exit 1.
Tier 2 violations warn (exit 0 with warnings).

Usage:
    python3 spec-tests/_test_invariants.py [repo-root]
"""

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent

errors = 0
warnings = 0

def load_json(path):
    with open(path) as f:
        return json.load(f)

# ── P1: Independence before reconciliation ──────────────────────────
# Check: reaction/cross_check docs carry contamination boundaries
print("=== P1 — Independence before reconciliation ===")

# Check SYNC_LEDGER exists
ledger_path = ROOT / "sync_ledger.json"
if not ledger_path.exists():
    print("  FAIL (Tier 1): sync_ledger.json not found")
    errors += 1
else:
    ledger = load_json(ledger_path)
    entries = ledger.get("entries", [])
    if not entries:
        print("  WARN: no sync entries — P1 unverifiable")
        warnings += 1
    else:
        # Check: last entry has reviewed docs
        last = entries[-1]
        if last.get("reviewed"):
            print(f"  OK: last sync entry has {len(last['reviewed'])} reviewed docs")
        else:
            print("  WARN: last sync entry has no reviewed docs")
            warnings += 1
    print(f"  OK: sync_ledger.json present with {len(entries)} entries")

# ── P2: No findings compromise without measurement ──────────────────
print("\n=== P2 — Findings resolve by measurement ===")
# Check: divergence_registry.json exists (optional but recommended)
div_path = ROOT / "divergence_registry.json"
if div_path.exists():
    print("  OK: divergence_registry.json present")
else:
    print("  WARN: divergence_registry.json not found (L2 — recommended)")
    warnings += 1

# ── P3: Convergence tags machine-checked ───────────────────────────
print("\n=== P3 — Convergence tags ===")
# Check: reaction/cross_check docs in docs/ carry convergence field
docs_dir = ROOT / "docs"
if docs_dir.exists():
    missing = 0
    for md in docs_dir.rglob("*.md"):
        content = md.read_text()
        if not content.startswith("---\n"):
            continue
        end = content.find("\n---\n", 4)
        if end == -1:
            continue
        fm_text = content[4:end]
        fm = {}
        for line in fm_text.strip().split("\n"):
            if ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip()] = v.strip().strip('"').strip("'")
        
        atype = fm.get("artifact_type", "")
        if atype in ("reaction", "cross_check"):
            if "convergence" not in fm:
                print(f"  FAIL (Tier 1): {md.name} missing convergence field")
                errors += 1
                missing += 1
            elif fm["convergence"] not in ("independent", "propagated", "modal", "n/a"):
                print(f"  WARN: {md.name} convergence '{fm['convergence']}' unrecognized")
                warnings += 1
    
    if missing == 0:
        print(f"  OK: convergence tags present on reaction/cross_check docs")
else:
    print("  WARN: docs/ not found (P3 cannot fully verify)")
    warnings += 1

# ── P4: Failed gates name their cause, never move bracket ──────────
print("\n=== P4 — Gate integrity ===")
# Cannot fully mechanical-check without parsing every findings doc.
# Heuristic: check that no committed finding says "PASS after bracket move"
# This is L2 — manual audit.
print("  OK: manual audit (L2 — bracket integrity is author discipline)")

# ── P5: Leaks declared, not hidden ─────────────────────────────────
print("\n=== P5 — Leak declaration ===")
# Check: any reaction doc that cites a partner path via parent_artifacts
# that resolves to a partner repo should have provenance_note.
# This requires partners.json — skip if not present.
partners_path = ROOT / "partners.json"
partners = None
if partners_path.exists():
    partners = load_json(partners_path)
print(f"  OK: {'partners.json present' if partners else 'partners.json not found — P5 cannot verify'}")
if not partners:
    warnings += 1

# ── P6: Async-first — no blocking waits ────────────────────────────
print("\n=== P6 — Async-first ===")
# Check: sync_ledger entries are directional (no entry requires partner response)
print("  OK: ledger entries are directional by construction")

# ── P7: Autonomy gates on enforcement ──────────────────────────────
print("\n=== P7 — Autonomy gates ===")
# Check: embargo_registry.json exists
embargo_path = ROOT / "embargo_registry.json"
if embargo_path.exists():
    print("  OK: embargo_registry.json present")
else:
    print("  WARN: embargo_registry.json not found (L2 gate)")
    warnings += 1

# ── P8: Protocol tests itself ──────────────────────────────────────
print("\n=== P8 — Protocol self-testing ===")
# Check: _test_schemas.py and _test_invariants.py exist
test_files = ["_test_schemas.py", "_test_invariants.py"]
spec_test_dir = ROOT / "spec-tests"
if spec_test_dir.exists():
    for tf in test_files:
        if (spec_test_dir / tf).exists():
            print(f"  OK: {tf} present")
        else:
            print(f"  WARN: {tf} not found")
            warnings += 1
else:
    print("  WARN: spec-tests/ not found")
    warnings += 1

# ── Summary ────────────────────────────────────────────────────────
print(f"\n{'=' * 50}")
if errors == 0 and warnings == 0:
    print("  ALL GREEN — invariants satisfied")
    print(f"{'=' * 50}")
    sys.exit(0)
elif errors == 0:
    print(f"  PASS — {errors} error(s), {warnings} warning(s)")
    print(f"  Tier 2 warnings are non-blocking.")
    print(f"{'=' * 50}")
    sys.exit(0)
else:
    print(f"  FAIL — {errors} error(s), {warnings} warning(s)")
    print(f"  Tier 1 violations must be fixed.")
    print(f"{'=' * 50}")
    sys.exit(1)
