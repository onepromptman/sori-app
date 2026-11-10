"""Build public artifacts from a clean tracked-source snapshot, never a local app folder."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

SIDECARS = {
    "setup-auto-sweep.bat": "setup-auto-sweep.bat",
    "LICENSE": "LICENSE.txt",
    "READ ME FIRST.txt": "READ ME FIRST.txt",
    "THIRD-PARTY-NOTICES.md": "THIRD-PARTY-NOTICES.md",
    "PRIVACY.md": "PRIVACY.md",
}
PRIVATE_NAMES = {"engine", ".env", "credentials.json", "shows.json", "transcripts", "trainings"}


def snapshot(root: Path, target: Path) -> list[str]:
    """Copy tracked files only. Local changes are included for pre-release testing."""
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    paths = [p for p in paths if p]
    for name in paths:
        rel = PurePosixPath(name)
        if rel.is_absolute() or ".." in rel.parts or any(p.lower() in PRIVATE_NAMES for p in rel.parts):
            raise ValueError("A private or unsafe path is tracked. Public packaging refused.")
        src = root / name
        if src.is_symlink() or not src.is_file() or not src.resolve().is_relative_to(root.resolve()):
            raise ValueError("A tracked file is missing or points outside the checkout.")
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
    return paths


def zip_tree(source: Path, output: Path, prefix: str) -> None:
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, str(PurePosixPath(prefix) / path.relative_to(source).as_posix()))


def build(root: Path, windows_exe: bool = False) -> Path:
    """Use a new build folder each time; stale/private binaries cannot be reused."""
    parent = root / "build"
    parent.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="public-", dir=parent))
    source = stage / "source"
    source.mkdir()
    paths = snapshot(root, source)
    manifest = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in paths}
    output = stage / "release"
    output.mkdir()
    zip_tree(source, output / "Sori-browser.zip", "Sori")
    zip_tree(source, output / "Sori-source.zip", "Sori")
    # The plugin ZIP has its manifest at the root and includes the same source.
    zip_tree(source, output / "sori.zip", "")
    if windows_exe:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--noconfirm", "Sori.spec"],
            cwd=source,
            check=True,
        )
        dist = source / "dist/Sori"
        for src, dest in SIDECARS.items():
            shutil.copyfile(source / src, dist / dest)
        if not (dist / "Sori.exe").is_file():
            raise ValueError("The Windows executable is missing.")
        zip_tree(dist, output / "Sori-win64.zip", "Sori")
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    sums = "".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n"
        for p in sorted(output.iterdir())
        if p.is_file()
    )
    (output / "SHA256SUMS.txt").write_text(sums, encoding="utf-8")
    return output


def main(root: Path | None = None) -> int:
    if "--no-build" in sys.argv:
        print("Refused: public releases require a fresh build; existing dist folders cannot be re-zipped.")
        return 2
    try:
        output = build(root or Path(__file__).resolve().parent, windows_exe="--windows-exe" in sys.argv)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Public build failed ({type(exc).__name__}). No release is ready.", file=sys.stderr)
        return 1
    print(f"Prepared public artifacts: {output}")
    print("Review the artifacts and checksums before publishing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
