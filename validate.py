#!/usr/bin/env python3
"""Validate CANON EVENT structured output against the frozen contract.

Standard library only, deliberately. A clean clone must validate with nothing
installed: `git clone && python3 validate.py`. Adding a dependency here would
break the no-build-step promise that the whole "swap day is cp" architecture
rests on, and it would break the D6 clean-clone check.

Supports the JSON Schema subset the contract actually uses: type, required,
properties, additionalProperties, enum, $ref/$defs, pattern, minimum, minLength,
items, and format for date / date-time / uri.

Run:  python3 validate.py
      python3 validate.py data/fixture-v1.json
Exit code 0 if everything validates, 1 otherwise.
"""

import json
import re
import sys
import pathlib

ROOT = pathlib.Path(__file__).parent
SCHEMA_PATH = ROOT / "contract" / "row.schema.json"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
URI_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$")

TYPES = {
    "object": dict, "array": list, "string": str,
    "boolean": bool, "number": (int, float),
}


def resolve(node, root):
    """Follow a local $ref. Only same-document refs are used by the contract."""
    while "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/"):
            raise ValueError(f"only local refs supported, got {ref}")
        target = root
        for part in ref[2:].split("/"):
            target = target[part]
        node = target
    return node


def validate(instance, schema, root, path="$", errors=None):
    if errors is None:
        errors = []
    schema = resolve(schema, root)

    def fail(msg):
        errors.append(f"{path}: {msg}")

    t = schema.get("type")
    if t == "integer":
        # bool is a subclass of int in Python; a boolean is not an integer here.
        if isinstance(instance, bool) or not isinstance(instance, int):
            fail(f"expected integer, got {type(instance).__name__}")
            return errors
    elif t in TYPES:
        if t == "number" and isinstance(instance, bool):
            fail("expected number, got boolean")
            return errors
        if not isinstance(instance, TYPES[t]):
            fail(f"expected {t}, got {type(instance).__name__}")
            return errors

    if "enum" in schema and instance not in schema["enum"]:
        fail(f"{instance!r} not in {schema['enum']}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            fail(f"shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            fail(f"{instance!r} does not match {schema['pattern']}")
        fmt = schema.get("format")
        if fmt == "date" and not DATE_RE.match(instance):
            fail(f"{instance!r} is not a date")
        elif fmt == "date-time" and not DATETIME_RE.match(instance):
            fail(f"{instance!r} is not a date-time")
        elif fmt == "uri" and not URI_RE.match(instance):
            fail(f"{instance!r} is not a uri")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            fail(f"{instance} below minimum {schema['minimum']}")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                fail(f"missing required key {key!r}")
        props = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in props:
                    fail(f"unexpected key {key!r}")
        for key, sub in props.items():
            if key in instance:
                validate(instance[key], sub, root, f"{path}.{key}", errors)

    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            validate(item, schema["items"], root, f"{path}[{i}]", errors)

    return errors


def check_invariants(doc, name):
    """Contract rules that JSON Schema cannot express but the wall depends on."""
    problems = []
    rows = doc["rows"]
    stats = doc["stats"]

    if rows != sorted(rows, key=lambda r: -r["days"]):
        # ties are allowed to be broken by the secondary key, so only flag a real inversion
        prev = None
        for r in rows:
            if prev is not None and r["days"] > prev:
                problems.append(f"row {r['rank']} breaks DAY N descending order")
                break
            prev = r["days"]

    for r in rows:
        if r["tier"] == "RED" and "evidence" not in r:
            problems.append(f"row {r['rank']} is RED with no evidence block")
        if r["tier"] == "RED" and not any(v == "RED" for v in r["arms"].values()):
            problems.append(f"row {r['rank']} is RED but no arm reports RED")
        if r["tier"] == "AMBER" and "evidence" in r:
            problems.append(f"row {r['rank']} is AMBER but carries evidence")
        if set(r["arms"]) != {"US", "DE", "IN"}:
            problems.append(f"row {r['rank']} has arms {sorted(r['arms'])}, expected US/DE/IN")

    rc = stats["precision"]["recall"]
    if rc["n1_brand_model"] + rc["n2_model_only"] - rc["m_both"] != rc["observed"]:
        problems.append("capture-recapture counts do not reconcile to observed")
    if rc["n_hat"] < rc["observed"]:
        problems.append("capture-recapture N-hat is below the observed count")

    a = stats["arithmetic"]
    expected = a["corpus_seeds"] * a["queries_per_seed_per_arm"] * a["arms"]
    if a["search_page_loads"] != expected:
        problems.append(f"search loads {a['search_page_loads']} != {expected} (the multiplication a judge will do)")
    if a["total_page_loads"] != a["search_page_loads"] + a["pdp_promotions"]:
        problems.append("total page loads do not sum")
    if stats["credits"]["used"] != a["total_page_loads"]:
        problems.append("credits used does not equal page loads at 1 credit each")
    if stats["credits"]["used"] > stats["credits"]["cap"]:
        problems.append("credits used exceeds the cap")

    for key in ("survival", "unsearchable", "precision"):
        s = stats[key]
        if s.get("v") is not None and s.get("ci95"):
            lo, hi = s["ci95"]
            if not (lo <= s["v"] <= hi):
                problems.append(f"{key}: point estimate {s['v']} outside its own CI {s['ci95']}")

    aps = stats["adversarial_precision_set"]
    if not aps["all_discarded"]:
        problems.append("an adversarial near-miss reached RED: precision bug, blocks the freeze")

    if stats["arms_measured"]["n"] > stats["arms_measured"]["d"]:
        problems.append("arms measured exceeds arms total")

    return problems


def main():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    targets = [pathlib.Path(a) for a in sys.argv[1:]] or sorted((ROOT / "data").glob("fixture-*.json"))
    if not targets:
        print("no fixtures found", file=sys.stderr)
        return 1

    total_rows = 0
    failed = False
    for path in targets:
        doc = json.loads(path.read_text(encoding="utf-8"))
        errors = []
        for row in doc["rows"]:
            validate(row, schema, schema, f"{path.name} row {row['rank']}", errors)
        problems = check_invariants(doc, path.name)
        total_rows += len(doc["rows"])

        if errors or problems:
            failed = True
            print(f"FAIL {path.name}")
            for e in (errors + problems)[:20]:
                print(f"     {e}")
            if len(errors) + len(problems) > 20:
                print(f"     ... and {len(errors) + len(problems) - 20} more")
        else:
            missing = sum(1 for r in doc["rows"]
                          if r.get("evidence") and "dom_path" not in r["evidence"].get("assertion", {}))
            print(f"ok   {path.name}  {len(doc['rows'])} rows, "
                  f"{sum(1 for r in doc['rows'] if r['tier'] == 'RED')} RED, "
                  f"{missing} exercising the MISSING path")

    print(f"\n{total_rows} rows checked against contract/row.schema.json")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
