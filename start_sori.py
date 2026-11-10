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
    print("\nSORI | Your local browser app", flush=True)
    print("1 of 2: Checking setup. First-time downloads can take a few minutes.", flush=True)
    print("Keep this window open. Later starts reuse the installed components.\n", flush=True)
    try:
        python = preflight.ensure("browser")
    except preflight.NotReady as exc:
        print(f"Sori could not start: {exc}", file=sys.stderr)
        return 2
    if "--selftest" not in args:
        preflight.say(
            "2 of 2: Starting the local app."
            + ("" if "--no-browser" in args else " Your browser will open automatically.")
        )
        if "--no-browser" not in args:
            preflight.say("Sori prepares the default speech model in the background if needed.")
        preflight.say("If no tab opens, visit http://127.0.0.1:17654 (unless you changed SORI_PORT).")
        preflight.say("Keep this window open while using Sori. Use Settings > Stop when finished.")
    try:
        return subprocess.call([str(python), str(Path(__file__).with_name("app.py")), *args])
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
