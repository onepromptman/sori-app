#!/usr/bin/env python3
"""
package.py — build Sori.exe and assemble the shippable release zip.

Why this exists: PyInstaller only produces `dist/Sori/Sori.exe` + `_internal/`.
The things a downloader actually needs beside the exe -- setup-auto-sweep.bat
(which looks for `%~dp0Sori.exe`, so it only works INSIDE the folder), the
quick-start text, and the licence -- are not build outputs and were silently
missing from earlier release zips. README.md documented setup-auto-sweep.bat
as "in the unzipped folder" while no release ever contained it.

Usage:  py package.py            (build + assemble + zip)
        py package.py --no-build (re-assemble + zip an existing dist/Sori)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DIST = ROOT / "dist" / "Sori"
ZIP_STEM = "Sori-win64"

# (source in repo, name it must have beside Sori.exe)
SIDECARS = [
    ("setup-auto-sweep.bat", "setup-auto-sweep.bat"),
    ("LICENSE", "LICENSE.txt"),
    ("READ ME FIRST.txt", "READ ME FIRST.txt"),
    # OFL 1.1 requires the licence to travel with the bundled fonts.
    ("THIRD-PARTY-NOTICES.md", "THIRD-PARTY-NOTICES.md"),
]


def main() -> int:
    if "--no-build" not in sys.argv:
        print("== building (this takes a few minutes) ==")
        r = subprocess.run([sys.executable, "-m", "PyInstaller",
                            "--noconfirm", "Sori.spec"], cwd=ROOT)
        if r.returncode:
            print("!! PyInstaller failed", file=sys.stderr)
            return r.returncode

    if not (DIST / "Sori.exe").exists():
        print(f"!! {DIST / 'Sori.exe'} missing -- build first", file=sys.stderr)
        return 1

    print("== adding sidecar files ==")
    for src_name, dest_name in SIDECARS:
        src = ROOT / src_name
        if not src.exists():
            print(f"!! missing {src}", file=sys.stderr)
            return 1
        shutil.copy2(src, DIST / dest_name)
        print(f"   + {dest_name}")

    # Fail loudly rather than shipping another incomplete folder.
    missing = [d for _, d in SIDECARS if not (DIST / d).exists()]
    if missing:
        print(f"!! sidecars missing after copy: {missing}", file=sys.stderr)
        return 1

    print("== zipping ==")
    out = shutil.make_archive(str(ROOT / ZIP_STEM), "zip", str(ROOT / "dist"), "Sori")
    size_mb = Path(out).stat().st_size / 1e6
    print(f"\nready: {out}  ({size_mb:.0f}MB)")
    print("upload with:  gh release upload <tag> Sori-win64.zip --clobber")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
