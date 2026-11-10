#!/usr/bin/env python3
"""Prepare Sori's browser dependencies, then open the local app."""

from pathlib import Path
import subprocess
import sys

import preflight


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if any(arg not in {"--no-browser", "--selftest"} for arg in args):
        print("Supported options: --no-browser, --selftest", file=sys.stderr)
        return 2
    try:
        python = preflight.ensure("browser")
    except preflight.NotReady as exc:
        print(f"Sori could not start: {exc}", file=sys.stderr)
        return 2
    if "--selftest" not in args:
        for notice in preflight.notices("browser", "base.en"):
            preflight.say(notice)
        preflight.say("opening the local browser app; use Settings > Stop when finished")
    try:
        return subprocess.call([str(python), str(Path(__file__).with_name("app.py")), *args])
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
