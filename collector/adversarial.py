"""The adversarial precision set: near-misses the matcher must reject.

WHY
---
Precision is currently a claim: "0.94, hand-verified against 50 items". That is
an assertion about a sample. It does not demonstrate that the matcher DISCARDS
things, only that the things it kept were mostly right.

The sharpest attack on this project is that it publishes a public wall naming
live listings as hazards, so roughly (1-p)*n of those rows are false accusations
against identifiable sellers. The existing answer is a disclosure sentence. This
file is the other half: a set of deliberately confusable probes, generated from
the real corpus, every one of which MUST land in DISCARDED.

That turns asserted precision into demonstrated precision, and it gives the
video a beat that cannot be faked: feed the matcher things designed to fool it,
and watch it refuse them one by one.

NOT THE SAME THING AS THE NEGATIVE CANARIES
-------------------------------------------
The heal loop's negative canaries are dead listings, and they test the
COLLECTOR: a heal that makes everything match is as broken as one that matches
nothing. These probes are live, real, plausible products, and they test the
MATCHER. Different failure, different layer, different fixture.

FIVE CONFUSION CLASSES
----------------------
successor_sku          the recalled product's own replacement model
same_brand_diff_model  a sibling product from the same manufacturer
same_model_diff_brand  an unrelated product that reuses the model string
adjacent_gtin          a GTIN one digit away, which is a real neighbouring product
truncated_identifier   a prefix of the model, which a sloppy matcher accepts

Standard library only.
"""

import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "contract"))

from normalize import reassert, norm_needle  # noqa: E402

TRAILING_NUM = re.compile(r"^(.*?)(\d+)([A-Za-z]*)$")


def successor(model):
    """Increment the trailing number: PS-1000 -> PS-1001.

    This is the single most dangerous confusion in the whole system. A recalled
    product's replacement SKU is genuinely on sale, genuinely from the same
    brand, and differs by one character. If the matcher accepts it, we accuse a
    seller of shipping a hazard they specifically fixed.
    """
    m = TRAILING_NUM.match(model or "")
    if not m:
        return None
    head, num, tail = m.groups()
    return f"{head}{int(num) + 1:0{len(num)}d}{tail}"


def adjacent_gtin(gtin):
    """Change the last digit. Real GTINs are dense, so this is a real product."""
    if not gtin or len(gtin) < 8 or not gtin.isdigit():
        return None
    last = int(gtin[-1])
    return gtin[:-1] + str((last + 1) % 10)


def truncated(model):
    """A prefix. A matcher using `in` rather than a token boundary accepts it."""
    if not model or len(model) < 5:
        return None
    return model[:len(model) - 2]


def build(seeds, limit=24):
    """Generate probes from real recall notices."""
    probes = []
    by_brand = {}
    for s in seeds:
        b = (s.get("brand") or "").strip().lower()
        if b and len(b) > 2:
            by_brand.setdefault(b, []).append(s)

    for s in seeds:
        model, gtin = s.get("model"), s.get("gtin")

        # THE HARD ONE. The page carries a SUPERSTRING of the identifier we
        # searched for, e.g. we search PS-100 and the page reads PS-1000. A
        # naive substring match accepts it and we publish a hazard claim
        # against a seller shipping a different product. This class found a
        # real bug in reassert() and is the reason it is boundary-anchored.
        for ident in (gtin, model):
            if ident and len(str(ident)) >= 4:
                probes.append(_p(s, str(ident), "superstring_trap",
                                 "the page carries a LONGER identifier that contains ours as a prefix",
                                 page_override=f"Product details Item model number {ident}9 In stock"))
                break

        if model:
            n = successor(model)
            if n and norm_needle(n) != norm_needle(model):
                probes.append(_p(s, n, "successor_sku",
                                 "the recalled product's own replacement model, one digit away"))
            t = truncated(model)
            if t and norm_needle(t) != norm_needle(model):
                probes.append(_p(s, t, "truncated_identifier",
                                 "a prefix of the real model. A substring match accepts it."))

        if gtin:
            n = adjacent_gtin(gtin)
            if n:
                probes.append(_p(s, n, "adjacent_gtin",
                                 "a GTIN one digit away, which is a different real product"))

        siblings = [x for x in by_brand.get((s.get("brand") or "").lower(), [])
                    if x["ref"] != s["ref"] and x.get("model")
                    and norm_needle(x["model"]) != norm_needle(model or "")]
        if siblings:
            probes.append(_p(s, siblings[0]["model"], "same_brand_diff_model",
                             f"a different product from the same brand ({siblings[0]['ref']})"))

    # same_model_diff_brand: reuse one notice's model against another's page.
    with_model = [s for s in seeds if s.get("model")]
    for a, b in zip(with_model, with_model[1:]):
        if norm_needle(a["model"]) != norm_needle(b["model"]):
            other_brand = b.get("brand") or "Unrelated Co"
            probes.append(_p(a, a["model"], "same_model_diff_brand",
                             f"the right model string on a page naming a different "
                             f"manufacturer ({other_brand}). Model strings are not "
                             f"globally unique, so identity alone is not enough.",
                             page_override=f"Product details Item model number {a['model']} "
                                           f"Brand {other_brand} In stock"))
            break

    # Spread across classes rather than taking the first N of one kind.
    out, seen = [], {}
    for p in probes:
        k = p["kind"]
        if seen.get(k, 0) >= max(2, limit // 5):
            continue
        seen[k] = seen.get(k, 0) + 1
        out.append(p)
        if len(out) >= limit:
            break
    return out


def _p(seed, probe_needle, kind, why, page_from=None, page_override=None):
    """One probe. `page_text` imitates what the marketplace would return."""
    src = page_from or seed
    page = page_override or (f"Product details Item model number {probe_needle} "
                             f"Brand {src.get('brand') or 'n/a'} In stock")
    return {
        "against_ref": seed["ref"],
        "against_name": seed["name"],
        "real_identifier": seed.get("gtin") or seed.get("model"),
        "probe_identifier": probe_needle,
        "kind": kind,
        "why": why,
        # The page the matcher would fetch carries the PROBE's identifier, not
        # the recalled one. That is exactly the trap.
        "page_text": page,
        "expected_brand": seed.get("brand"),
        "expect": "DISCARDED",
    }


def run(probes):
    """Every probe must fail to re-assert. Any that passes is a precision bug."""
    results, leaked = [], []
    for p in probes:
        from normalize import brand_conflict
        matched = reassert(p["page_text"], p["real_identifier"])
        if matched and brand_conflict(p["page_text"], p.get("expected_brand")):
            matched = False
        verdict = "RED" if matched else "DISCARDED"
        ok = verdict == p["expect"]
        results.append({**p, "verdict": verdict, "passed": ok})
        if not ok:
            leaked.append(p)
    return {
        "n": len(results),
        "all_discarded": not leaked,
        "leaked": leaked,
        "by_kind": {k: sum(1 for r in results if r["kind"] == k) for k in
                    sorted({r["kind"] for r in results})},
        "probes": results,
        "note": ("Deliberately confusable near-misses fed to the matcher. Every one must land "
                 "in DISCARDED. Any that reaches RED is a precision bug and blocks the freeze. "
                 "Distinct from the heal loop's negative canaries, which are dead listings "
                 "testing the collector rather than live products testing the matcher."),
    }


def main():
    sf = HERE.parent / "data" / "seeds.json"
    seeds = json.loads(sf.read_text(encoding="utf-8"))["seeds"]
    probes = build(seeds)
    res = run(probes)

    out = HERE.parent / "data" / "adversarial.json"
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  {res['n']} probes generated from real recall notices")
    for k, n in res["by_kind"].items():
        print(f"    {k:<24} {n}")
    print()
    for p in res["probes"][:5]:
        print(f"    {p['real_identifier']:<18} vs {p['probe_identifier']:<18} "
              f"{p['kind']:<22} -> {p['verdict']}")
    print()
    if res["all_discarded"]:
        print(f"  ALL {res['n']} REJECTED. Precision is demonstrated, not asserted.")
    else:
        print(f"  {len(res['leaked'])} LEAKED TO RED. Precision bug, blocks the freeze:")
        for p in res["leaked"]:
            print(f"    {p['real_identifier']} accepted {p['probe_identifier']} ({p['kind']})")
    print(f"\n  wrote data/adversarial.json")
    return 0 if res["all_discarded"] else 1


if __name__ == "__main__":
    sys.exit(main())
