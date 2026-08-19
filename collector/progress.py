#!/usr/bin/env python3
"""Live progress for sweeps in flight. A terminal view, deliberately not a page.

WHY THIS IS NOT ON THE WALL
---------------------------
The wall reads a static JSON payload and never calls a backend. That is the whole
architecture: swap day is `cp`, a judge opens the file with no setup, and there is
no server to ask "how is the sweep going". A live progress bar on that page would
require inventing one.

It would also be the wrong thing to publish. The wall is a filed finding, and how
long the collection took is an operational fact, not a result. What the wall
already carries is the sweep's state AS OF PUBLICATION — the arms, their verdicts,
what each returned — which is the part a reader needs in order to judge the
figures.

So progress lives here, in the terminal, for the person running it.

WHAT MAKES IT ACCURATE RATHER THAN DECORATIVE
---------------------------------------------
A progress bar that interpolates is a guess with a rectangle around it. Every
number below is counted from something already on disk:

  planned batches   recomputed from the same plan_arm() the sweep runs, so the
                    denominator is the real one rather than an estimate
  finished batches  parsed from the sweep's own stdout, which prints one line per
                    completed batch
  listings          line count of the raw archive, which is written on receipt
  spend             the account balance, read live, against a recorded start

Nothing is projected. A batch is either finished or it is not, and an unfinished
batch shows as unfinished for however long it takes — including the hour a
40-URL amazon.com batch spent timing out, which is the truth and is worth seeing.

Run:  python3 collector/progress.py            once
      python3 collector/progress.py --watch    refresh every 20s
"""

import json
import pathlib
import re
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from sweep import ARM_SEARCH, COLLECTORS, BATCH_SIZE, load_seeds, plan_arm  # noqa: E402

RAW = ROOT / "data" / "sweeps" / "raw"

# Where a running sweep writes its stdout. Several are checked because arms can be
# launched separately to run in parallel, which is how a three-arm sweep is
# actually driven.
LOG_CANDIDATES = [
    pathlib.Path("/tmp/sweep-%s.log"),
    pathlib.Path("/tmp/sweep_%s.log"),
]

BATCH_LINE = re.compile(
    r"^\s*([A-Z]{2})\s+batch\s+(\d+)\s+(\d+)\s+urls\s+->\s+(\d+)\s+rows\s*(.*)$")


def logs_for(arm):
    for pattern in LOG_CANDIDATES:
        path = pathlib.Path(str(pattern).replace("%s", arm))
        if path.exists():
            return path
    return None


def batches_done(arm):
    """Every completed batch for this arm, parsed from the sweep's own output.

    Returns a list of (n, urls, rows, note). A batch appears here only once the
    job returned, so a batch still in flight is absent rather than partial — which
    is the honest shape: there is no such thing as a half-finished job.
    """
    path = logs_for(arm)
    if not path:
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = BATCH_LINE.match(line)
        if m:
            out.append((int(m.group(2)), int(m.group(3)), int(m.group(4)),
                        m.group(5).strip()))
    return out


def archived(arm):
    path = RAW / ("%s.jsonl" % arm)
    if not path.exists():
        return 0
    with path.open("rb") as fh:
        return sum(1 for _ in fh)


def running():
    """Which arms have a sweep process alive right now."""
    try:
        ps = subprocess.run(["ps", "-eo", "command"], capture_output=True,
                            text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return set()
    live = set()
    for line in ps.splitlines():
        if "collector/sweep.py" not in line or "progress.py" in line:
            continue
        m = re.search(r"--arms\s+([A-Z,]+)", line)
        if m:
            live |= {a for a in m.group(1).split(",") if a}
        else:
            # No --arms means every configured arm.
            live |= set(COLLECTORS)
    return live


def balance():
    """Account balance, live. Returns None rather than guessing if the CLI is slow."""
    try:
        out = subprocess.run(
            ["npx", "-p", "@brightdata/cli", "bdata", "budget"],
            capture_output=True, text=True, timeout=90).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"Balance\s+\$?([\d.]+)", out)
    return float(m.group(1)) if m else None


def bar(done, total, width=28):
    """A bar drawn from counted values only. No interpolation, no easing."""
    if not total:
        return "·" * width
    filled = int(round(width * min(1.0, done / total)))
    return "█" * filled + "·" * (width - filled)


def render(limit=None, start_balance=None):
    seeds = load_seeds(limit=limit)
    live = running()
    lines = []

    lines.append("CANON EVENT · sweep progress")
    lines.append("%d notices in scope%s" % (len(seeds),
                                            "  (trial slice)" if limit else ""))
    lines.append("")

    total_planned = total_done = total_rows = 0
    for arm in sorted(ARM_SEARCH):
        planned_loads = len(plan_arm(arm, seeds))
        planned = (planned_loads + BATCH_SIZE - 1) // BATCH_SIZE
        done = batches_done(arm)
        rows = archived(arm)
        total_planned += planned
        total_done += len(done)
        total_rows += rows

        has_log = logs_for(arm) is not None
        state = "running" if arm in live else ("done" if done else "idle")
        if not has_log:
            # No stdout to read. The archive still says what arrived, and claiming
            # 0 of 3 batches for an arm holding 1,066 listings would be the same
            # error as rendering an absent field as zero.
            state = "archived, no log" if rows else "not started"
            lines.append("  %-3s %s  batches unknown   %6d listings   %s"
                         % (arm, bar(1 if rows else 0, 1), rows, state))
            lines.append("")
            continue
        lines.append("  %-3s %s  %d/%d batches   %6d listings   %s"
                     % (arm, bar(len(done), planned), len(done), planned, rows, state))

        for n, urls, got, note in done:
            flag = "  <- %s" % note if note else ""
            lines.append("        batch %-2d %3d urls -> %6d rows%s" % (n, urls, got, flag))
        if arm in live and len(done) < planned:
            lines.append("        batch %-2d in flight, no result yet"
                         % (len(done) + 1))
        lines.append("")

    lines.append("  total  %s  %d/%d batches   %d listings archived"
                 % (bar(total_done, total_planned), total_done, total_planned,
                    total_rows))

    bal = balance()
    if bal is not None:
        spent = ("  spent $%.2f" % (start_balance - bal)) if start_balance else ""
        lines.append("  balance $%.2f%s" % (bal, spent))

    if not live:
        lines.append("")
        lines.append("  nothing in flight. Re-score everything already archived,")
        lines.append("  for free, with:  python3 collector/sweep.py --from-raw")
    return "\n".join(lines)


def main(argv):
    limit = None
    watch = "--watch" in argv
    for i, a in enumerate(argv):
        if a == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1])

    if not watch:
        print(render(limit))
        return 0

    start = balance()
    try:
        while True:
            # Clear and redraw rather than scroll, so the terminal shows one live
            # view instead of a history nobody reads.
            sys.stdout.write("\033[2J\033[H")
            sys.stdout.write(render(limit, start))
            sys.stdout.write("\n\n  refreshing every 20s · ctrl-c to stop\n")
            sys.stdout.flush()
            time.sleep(20)
    except KeyboardInterrupt:
        print()
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
