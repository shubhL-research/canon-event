"""Refuse stray control characters in source files.

WHY THIS EXISTS
---------------
test_render.js carried a guard meant to stop a retracted claim ("residential
exit IPs") from being republished. The guard read:

    const RETRACTED = /\b(from|via|using|through|on|over)\s+residential/i;

except that the file did not contain a backslash and a `b`. It contained a
single 0x08 BACKSPACE byte, written there by a shell heredoc that collapsed the
escape. The regex therefore demanded a literal control character before the word
"from" and could never match anything. It passed every run, on a file that was
at that moment publishing the exact claim it existed to forbid.

A test that cannot fail is worse than no test: it occupies the space where a
real check would go and reports success while doing nothing. The failure is
invisible by construction, because the only symptom is a pass.

So the bytes are checked directly. Escapes are written as escapes, or the build
stops.

    python3 check_sources.py
"""

import pathlib
import sys

# 0x08 is the one that actually bit. The rest are here because they arrive by
# the same route and are equally invisible in an editor.
FORBIDDEN = {8: "BACKSPACE", 7: "BEL", 12: "FORMFEED", 27: "ESC", 0: "NUL"}

# Fetched pages and raw platform output are evidence, not source. They are
# committed exactly as received and must never be rewritten to please a linter.
SKIP = ("node_modules", ".git", "data/sweeps", "data/hunt/", "data/attest")

PATTERNS = ("*.js", "*.py", "*.html", "*.css", "*.md", "*.json", "*.sh")


def main():
    root = pathlib.Path(__file__).resolve().parent
    hits, scanned = [], 0
    for pat in PATTERNS:
        for f in sorted(root.rglob(pat)):
            rel = f.relative_to(root).as_posix()
            if any(s in rel for s in SKIP):
                continue
            scanned += 1
            raw = f.read_bytes()
            for code, name in FORBIDDEN.items():
                n = raw.count(bytes([code]))
                if n:
                    line = raw[:raw.index(bytes([code]))].count(b"\n") + 1
                    hits.append((rel, name, n, line))

    print("  %d source files scanned" % scanned)
    if not hits:
        print("  no stray control characters")
        return 0

    print("\n  STRAY CONTROL CHARACTERS, almost certainly a collapsed escape:\n")
    for rel, name, n, line in hits:
        print("    %-44s %s x%d, first at line %d" % (rel, name, n, line))
    print("\n  A \b that became 0x08 makes a regex that can never match, and a"
          "\n  check that can never fail. Write the escape, do not paste the byte.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
