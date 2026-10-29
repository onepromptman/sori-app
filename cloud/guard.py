#!/usr/bin/env python3
"""Captions-only guard for the cloud sweep.

The cloud runner installs requirements-captions.txt, which has no
faster-whisper, so any RSS/audio show in the cloud subscription list would
fail on every sweep and burn its retry budget. Refuse to run instead.

Reads $SORI_HOME/shows.json directly (no import of app.py: no dependencies,
no side effects, no state migration). Exit codes: 0 ok (including a missing
file or zero shows), 3 when any show is not a YouTube show.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    home = os.environ.get("SORI_HOME")
    if not home:
        print("!! guard: SORI_HOME is not set", file=sys.stderr)
        return 3
    path = Path(home) / "shows.json"
    if not path.exists():
        print(f"guard: no shows.json at {path} (nothing to sweep)")
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"!! guard: cannot read {path}: {exc}", file=sys.stderr)
        return 3

    shows = data.get("shows") or []
    # app.load_store() defaults a missing "type" to "rss", so treat a missing
    # key the same way the engine would: as an audio show.
    offenders = [s for s in shows if s.get("type", "rss") != "youtube"]
    if offenders:
        names = ", ".join(f"{s.get('name', '?')} ({s.get('type', 'rss')})" for s in offenders)
        print(
            "!! guard: the cloud sweep is captions-only (no Whisper). "
            f"Remove these non-YouTube shows from state/shows.json: {names}",
            file=sys.stderr,
        )
        return 3
    print(f"guard: {len(shows)} show(s), all youtube")
    return 0


if __name__ == "__main__":
    sys.exit(main())
