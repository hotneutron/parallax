#!/usr/bin/env python3
"""Minimal JSON-Schema-subset validator (dependency-free) shared by the
conformance suite. Supports: type, required, properties, items, enum,
additionalProperties (bool or schema), const, allOf, if/then/else,
pattern, minLength, minProperties.
Returns a list of error strings."""
import re
_TY = {"object": dict, "array": list, "string": str, "integer": int,
       "number": (int, float), "boolean": bool, "null": type(None)}


def validate(inst, schema, path="$"):
    errs = []
    t = schema.get("type")                      # str OR list (e.g. ["string","null"])
    if t is not None:
        types = [t] if isinstance(t, str) else list(t)
        known = [x for x in types if x in _TY]
        if known:
            bad_bool = isinstance(inst, bool) and "boolean" not in known and \
                ("integer" in known or "number" in known)
            if bad_bool or not any(isinstance(inst, _TY[x]) for x in known):
                return [f"{path}: expected {t}, got {type(inst).__name__}"]
    if "enum" in schema and inst not in schema["enum"]:
        errs.append(f"{path}: {inst!r} not in enum {schema['enum']}")
    if "const" in schema and inst != schema["const"]:
        errs.append(f"{path}: {inst!r} != const {schema['const']!r}")
    if isinstance(inst, str):
        if "pattern" in schema and not re.search(schema["pattern"], inst):
            errs.append(f"{path}: {inst!r} does not match pattern {schema['pattern']!r}")
        if "minLength" in schema and len(inst) < schema["minLength"]:
            errs.append(f"{path}: shorter than minLength {schema['minLength']}")
    # required/properties apply to any object instance (not only when type:object is declared —
    # `if`/`then` subschemas omit type but still constrain required/properties)
    if isinstance(inst, dict):
        if "minProperties" in schema and len(inst) < schema["minProperties"]:
            errs.append(f"{path}: {len(inst)} properties, fewer than minProperties {schema['minProperties']}")
        for r in schema.get("required", []):
            if r not in inst:
                errs.append(f"{path}.{r}: required field missing")
        props, ap = schema.get("properties", {}), schema.get("additionalProperties")
        for k, v in inst.items():
            if k in props:
                errs += validate(v, props[k], f"{path}.{k}")
            elif isinstance(ap, dict):
                errs += validate(v, ap, f"{path}.{k}")
            elif ap is False:
                errs.append(f"{path}.{k}: additional property not allowed")
    if isinstance(inst, list) and "items" in schema:
        for i, it in enumerate(inst):
            errs += validate(it, schema["items"], f"{path}[{i}]")
    for sub in schema.get("allOf", []):
        errs += validate(inst, sub, path)
    if "if" in schema:
        if not validate(inst, schema["if"], path):      # instance matches `if` (validates clean)
            errs += validate(inst, schema.get("then", {}), path)
        elif "else" in schema:
            errs += validate(inst, schema["else"], path)
    return errs
