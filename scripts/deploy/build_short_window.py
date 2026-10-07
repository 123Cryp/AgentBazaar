#!/usr/bin/env python3
"""
Writes build/job_market_short_window.py: the JobMarket contract with its time windows shortened so a whole job
lifecycle (bid window, selection grace, link window) fits in minutes on GenLayer Studio.

    python3 scripts/deploy/build_short_window.py [seconds_per_unit]   # default 60

The only change is the WINDOW_UNIT constant (3600 -> N). Test networks only: never deploy the short-window build
with real funds or as the production market. The script refuses to write unless the diff against
contracts/job_market.py is exactly that one line. AgentRegistry and ReputationLedger have no time windows, so they
are deployed unchanged.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "contracts", "job_market.py")
OUT = os.path.join(ROOT, "build", "job_market_short_window.py")


def render(unit):
    with open(SRC, encoding="utf-8") as fh:
        src = fh.read()
    old = "WINDOW_UNIT = 3600\n"
    if src.count(old) != 1:
        raise SystemExit("WINDOW_UNIT line not found exactly once")
    out = src.replace(old, "WINDOW_UNIT = %d\n" % unit)
    diff = [(a, b) for a, b in zip(src.split("\n"), out.split("\n")) if a != b]
    if len(diff) != 1:
        raise SystemExit("unexpected diff")
    return out


def main(argv):
    unit = int(argv[0]) if argv else 60
    if unit < 1 or unit >= 3600:
        raise SystemExit("seconds_per_unit must be between 1 and 3599")
    out = render(unit)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(out)
    print("wrote %s with WINDOW_UNIT = %d (min bid window %d s, selection grace %d s, link window %d s)"
          % (os.path.relpath(OUT, ROOT), unit, 2 * unit, 12 * unit, 12 * unit))


if __name__ == "__main__":
    main(sys.argv[1:])
