"""Every colour the finding act puts on its dark ground must be readable there.

WHY THIS EXISTS
---------------
The finding act is the only dark surface in this interface. Every other rule in
the stylesheet is written for paper, so a rule added to that act inherits the
wrong tokens by default and nothing catches it: the page still renders, the text
is still there, it is simply too dark to read against a graphite ground.

That happened. `.found-anyway`, which is the first screen and the first thing on
camera, was written with the light-ground inks. Body text measured 2.13:1 and the
only link in the act measured 1.08:1, which is invisible. The pointer cursor was
the only thing telling a reader it could be clicked at all.

Numbers are WCAG 2.1 contrast ratios. AA is 4.5:1 for normal text and 3:1 for
large text, where large means 18.66px and bold, or 24px.

    python3 check_contrast.py
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent


def _lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def tokens():
    css = (ROOT / "contract" / "tokens.css").read_text(encoding="utf-8")
    return {m.group(1): m.group(2)
            for m in re.finditer(r"(--[\w-]+):\s*(#[0-9A-Fa-f]{3,8})\s*;", css)}


def main():
    t = tokens()
    ground = t.get("--hero-ground")
    if not ground:
        print("  --hero-ground not found in tokens.css")
        return 1

    # Every foreground the finding act actually uses, with the size it uses it at.
    # 4.5 unless the type is large enough for the 3:1 threshold.
    CASES = [
        ("hero heading",        t["--ink-inv"],        3.0, "clamp(38px+), large"),
        ("found-anyway body",   "#C9CDD1",             4.5, "15px normal"),
        ("found-anyway bold",   t["--hazard-on-dark"], 4.5, "15px bold, under the large threshold"),
        ("found-anyway link",   t["--ink-inv"],        4.5, "15px normal"),
    ]

    print("  finding act ground %s\n" % ground)
    bad = []
    for label, colour, need, note in CASES:
        r = contrast(colour, ground)
        ok = r >= need
        if not ok:
            bad.append((label, colour, r, need))
        print("    %-20s %-9s %6.2f:1  needs %.1f  %s   %s"
              % (label, colour, r, need, "ok  " if ok else "FAIL", note))

    # The dark-ground red must stay the same colour, not become a different one.
    h1, h2 = t["--hazard"], t["--hazard-on-dark"]
    import colorsys
    def hue(x):
        x = x.lstrip("#")
        r, g, b = (int(x[i:i + 2], 16) / 255 for i in (0, 2, 4))
        return colorsys.rgb_to_hls(r, g, b)[0] * 360
    drift = abs(hue(h1) - hue(h2))
    print("\n    hazard hue on paper %.1f deg, on dark %.1f deg, drift %.1f"
          % (hue(h1), hue(h2), drift))
    if drift > 3:
        bad.append(("hazard-on-dark hue drift", h2, drift, 3))

    if bad:
        print("\n  BELOW THRESHOLD:\n")
        for label, colour, r, need in bad:
            print("    %s: %s is %.2f, needs %.2f" % (label, colour, r, need))
        return 1
    print("\n  every finding-act colour clears AA on its own ground")
    return 0


if __name__ == "__main__":
    sys.exit(main())
