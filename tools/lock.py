#!/usr/bin/env python3
"""Regenerate requirements.lock from the pins in pyproject.toml.

Walks importlib.metadata's ``requires()`` from the direct pins (the core
dependencies plus the ``app`` and ``dev`` groups) over whatever is installed
on THIS interpreter and writes every reached distribution as ``name==version``,
sorted, one per line. Requirements gated on an extra are skipped; other
environment markers are evaluated with ``packaging`` when it is installed
(it is, as a matplotlib dependency) and otherwise resolved by "is it
installed here".

    py tools/lock.py            # writes requirements.lock
    py tools/lock.py --check    # exit 1 if the file is stale
"""
from __future__ import annotations

import re
import sys
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("app", "dev")
HEADER = "# generated on Windows / CPython 3.14 from pyproject pins; regenerate with tools/lock.py\n"

_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _wanted(req: str) -> bool:
    """False for requirements only pulled in by an extra or a false marker."""
    if ";" not in req:
        return True
    marker = req.split(";", 1)[1].strip()
    if "extra" in marker:
        return False
    try:
        from packaging.markers import Marker
        return bool(Marker(marker).evaluate())
    except Exception:
        return True  # fall through to the "is it installed" check


def direct_pins() -> list[str]:
    proj = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pins = list(proj["dependencies"])
    for g in GROUPS:
        pins += proj["optional-dependencies"][g]
    return pins


def closure(pins: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    todo = [_NAME.match(p).group(1) for p in pins]
    while todo:
        name = todo.pop()
        key = _norm(name)
        if key in out:
            continue
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue  # optional on this platform, or a false marker
        out[key] = f"{dist.metadata['Name']}=={dist.version}"
        for req in dist.requires or ():
            if _wanted(req):
                todo.append(_NAME.match(req).group(1))
    return out

# Direct pins must match what is installed; anything else means the lock
# would silently describe a different environment than pyproject promises.
def check_pins(pins: list[str], found: dict[str, str]) -> list[str]:
    bad = []
    for p in pins:
        name, _, ver = p.partition("==")
        got = found.get(_norm(name))
        if got is None or got.split("==")[1] != ver:
            bad.append(f"{p} (installed: {got or 'missing'})")
    return bad


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    pins = direct_pins()
    found = closure(pins)
    bad = check_pins(pins, found)
    if bad:
        print("!! pyproject pins differ from the installed versions:", file=sys.stderr)
        for b in bad:
            print("   " + b, file=sys.stderr)
        return 1
    body = HEADER + "".join(found[k] + "\n" for k in sorted(found))
    target = ROOT / "requirements.lock"
    if "--check" in argv:
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != body:
            print("!! requirements.lock is stale; run: py tools/lock.py", file=sys.stderr)
            return 1
        print("requirements.lock is current")
        return 0
    target.write_text(body, encoding="utf-8", newline="\n")
    print(f"wrote {target.relative_to(ROOT)} ({len(found)} distributions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
