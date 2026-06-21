#!/usr/bin/env python3
"""
Parallax schema conformance test — validates live cross_team/ data
against the frozen interop schemas. Dependency-free (no jsonschema
library needed — manual structural checks). Both teams write their
own implementation; the schema files are the shared contract.

Usage:
    python3 methodology/cross_team/_test_schemas.py
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMAS_DIR = HERE / "schemas"

def load(path):
    with open(path) as f:
        return json.load(f)

def check_type(value, expected_type, path):
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float))
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "bool":
        return isinstance(value, bool)
    return False

def check_pattern(value, pattern, path):
    return bool(re.match(pattern, str(value) if value else ""))

errors = 0
warnings = 0

# ── Validate partners.json ──────────────────────────────────────────
print("=== Validating partners.json ===")
partners = load(HERE / "partners.json")
schema = load(SCHEMAS_DIR / "partners.schema.json")

for req in schema.get("required", []):
    if req not in partners:
        print(f"  FAIL: missing required field '{req}'")
        errors += 1
    else:
        print(f"  OK: required field '{req}' present")

partners_data = partners.get("partners", {})
for name, p in partners_data.items():
    for req in schema["properties"]["partners"]["additionalProperties"]["required"]:
        if req not in p:
            print(f"  FAIL: partner '{name}' missing required field '{req}'")
            errors += 1
    if "protocol_version" in p:
        if not check_pattern(p["protocol_version"], r"^\d+\.\d+$", f"partners.{name}.protocol_version"):
            print(f"  FAIL: partner '{name}' protocol_version '{p['protocol_version']}' doesn't match pattern")
            errors += 1
    if "last_pinned" in p and p["last_pinned"]:
        if not check_pattern(p["last_pinned"], r"^[0-9a-f]{7,40}$", f"partners.{name}.last_pinned"):
            print(f"  FAIL: partner '{name}' last_pinned doesn't match hex pattern")
            errors += 1
    print(f"  OK: partner '{name}' ({p.get('team_name', '?')}) protocol v{p.get('protocol_version', '?')}")

if errors == 0:
    print(f"  PASS — partners.json validates\n")

# ── Validate sync_ledger.json ───────────────────────────────────────
print("=== Validating sync_ledger.json ===")
ledger = load(HERE / "sync_ledger.json")
schema = load(SCHEMAS_DIR / "ledger.schema.json")

for req in schema.get("required", []):
    if req not in ledger:
        print(f"  FAIL: missing required field '{req}'")
        errors += 1
    else:
        print(f"  OK: required field '{req}' present ({len(ledger[req])} entries)")

for i, entry in enumerate(ledger.get("entries", [])):
    for req in schema["properties"]["entries"]["items"]["required"]:
        if req not in entry:
            print(f"  FAIL: entry {i} missing required field '{req}'")
            errors += 1
    if entry.get("date"):
        if not check_pattern(entry["date"], r"^\d{4}-\d{2}-\d{2}$", f"entries[{i}].date"):
            print(f"  FAIL: entry {i} date '{entry['date']}' format")
            errors += 1
    if entry.get("their_head"):
        if not check_pattern(entry["their_head"], r"^[0-9a-f]{7,40}$", f"entries[{i}].their_head"):
            print(f"  FAIL: entry {i} their_head format")
            errors += 1
    if entry.get("our_head"):
        if not check_pattern(entry["our_head"], r"^[0-9a-f]{7,40}$", f"entries[{i}].our_head"):
            print(f"  FAIL: entry {i} our_head format")
            errors += 1

if errors == 0:
    print(f"  PASS — sync_ledger.json validates ({len(ledger['entries'])} entries)\n")

# ── Validate embargo_registry.json ──────────────────────────────────
print("=== Validating embargo_registry.json ===")
embargo = load(HERE / "embargo_registry.json")
schema = load(SCHEMAS_DIR / "embargo.schema.json")

for req in schema.get("required", []):
    if req not in embargo:
        print(f"  FAIL: missing required field '{req}'")
        errors += 1
    else:
        print(f"  OK: required field '{req}' present ({len(embargo.get(req, []))} topics)")

for i, topic in enumerate(embargo.get("topics", [])):
    for req in schema["properties"]["topics"]["items"]["required"]:
        if req not in topic:
            print(f"  FAIL: topic {i} missing required field '{req}'")
            errors += 1
    if topic.get("active_until"):
        if not check_pattern(topic["active_until"], r"^\d{4}-\d{2}-\d{2}$", f"topics[{i}].active_until"):
            print(f"  FAIL: topic {i} active_until format")
            errors += 1

if errors == 0:
    print(f"  PASS — embargo_registry.json validates\n")

# ── Summary ─────────────────────────────────────────────────────────
print(f"{'=' * 50}")
if errors == 0:
    print(f"  ALL GREEN — {errors} error(s), {warnings} warning(s)")
    print(f"  Schema seed validation: PASS")
    print(f"{'=' * 50}")
    sys.exit(0)
else:
    print(f"  FAIL — {errors} error(s), {warnings} warning(s)")
    print(f"{'=' * 50}")
    sys.exit(1)
