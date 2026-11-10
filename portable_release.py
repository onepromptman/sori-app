"""Build double-click Sori ZIPs with their own Python and preinstalled wheels."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

import public_release

PYTHON = "3.12.16"
RUNTIME_RELEASE = "20261026"
TARGETS = {
    "windows": (
        "x86_64-pc-windows-msvc",
        "Sori-Windows.zip",
        "590dfcbe3a34c07301e6332e13e2188b98655cd072b08afa45a7998dc4c22bc5",
    ),
    "mac-arm": (
        "aarch64-apple-darwin",
        "Sori-Mac-Apple-Silicon.zip",
        "fbf4afef53c2a6b72bb741bc06d5671a9dfaf87bd84e5aa73ac9b3d0d589f14e",
    ),
    "mac-intel": (
        "x86_64-apple-darwin",
        "Sori-Mac-Intel.zip",
        "a962e47df522889eaa7ff0d6a56203f1079f68aabb65ffdbe8455f362bc769f3",
    ),
}


def sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def python_archive(cache: Path, platform: str, digest: str) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    filename = f"cpython-{PYTHON}+{RUNTIME_RELEASE}-{platform}-install_only.tar.gz"
    target = cache / filename
    if target.exists():
        if sha256(target) != digest:
            raise ValueError(f"Runtime checksum mismatch: {filename}")
        return target
    url = (
        "https://github.com/astral-sh/python-build-standalone/releases/download/"
        f"{RUNTIME_RELEASE}/{filename.replace('+', '%2B')}"
    )
    with tempfile.NamedTemporaryFile(dir=cache, suffix=".part", delete=False) as file:
        partial = Path(file.name)
        with urllib.request.urlopen(url, timeout=60) as response:
            shutil.copyfileobj(response, file)
    if sha256(partial) != digest:
        raise ValueError(f"Runtime checksum mismatch: {filename}")
    partial.replace(target)
    return target


def add_runtime(zip_file: zipfile.ZipFile, runtime: Path, site: PurePosixPath) -> None:
    # Keep Unix permissions and relative symlinks in the ZIP even on a Windows
    # build host. Finder's unzip restores both. No upstream code runs here.
    with tarfile.open(runtime, "r:gz") as archive:
        for member in archive:
            original = PurePosixPath(member.name)
            if original.parts[0] != "python" or ".." in original.parts:
                raise ValueError("Unexpected path in the pinned Python archive")
            path = original.relative_to("python")
            if path == site or site in path.parents or member.isdir():
                continue
            name = "Sori/runtime/" + path.as_posix()
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            if member.issym():
                link = PurePosixPath(member.linkname)
                if link.is_absolute() or ".." in link.parts:
                    raise ValueError("Unexpected symlink in the pinned Python archive")
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                zip_file.writestr(info, member.linkname)
            elif member.isfile() or member.islnk():
                info.external_attr = (stat.S_IFREG | (member.mode & 0o755)) << 16
                contents = archive.extractfile(member)
                if contents is None:
                    raise ValueError(f"Unreadable Python archive entry: {name}")
                with contents, zip_file.open(info, "w") as out:
                    shutil.copyfileobj(contents, out)
            else:
                raise ValueError(f"Unexpected Python archive entry: {name}")


def build_target(source: Path, stage: Path, output: Path, cache: Path, target: str) -> Path:
    platform, filename, digest = TARGETS[target]
    windows = target == "windows"
    suffix = "bat" if windows else "command"
    site = PurePosixPath("Lib/site-packages" if windows else "lib/python3.12/site-packages")
    runtime = python_archive(cache, platform, digest)
    lock = source / "requirements.lock"
    if target == "mac-intel":
        # ONNX Runtime stopped publishing Intel Mac wheels after 1.23.2.
        lock = stage / "requirements-mac-intel.lock"
        lock.write_text(
            (source / "requirements.lock")
            .read_text(encoding="utf-8")
            .replace(
                "onnxruntime==1.26.0\n",
                "onnxruntime==1.23.2\ncoloredlogs==15.0.1\nhumanfriendly==10.0\nmpmath==1.3.0\nsympy==1.14.0\n",
            ),
            encoding="utf-8",
        )
    dependencies = tomllib.loads((source / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "dependencies"
    ]
    wheels = stage / target
    env = {**os.environ, "UV_LINK_MODE": "copy", "MACOSX_DEPLOYMENT_TARGET": "14.0"}
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--target",
            str(wheels),
            "--python-platform",
            platform,
            "--python-version",
            PYTHON,
            "--only-binary",
            ":all:",
            "-c",
            str(lock),
            *dependencies,
        ],
        env=env,
        check=True,
    )
    output.mkdir(parents=True, exist_ok=True)
    result = output / filename
    partial = result.with_suffix(".zip.part")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as bundle:
        launcher = zipfile.ZipInfo(f"Sori/START SORI.{suffix}")
        launcher.create_system = 3
        launcher.external_attr = (stat.S_IFREG | 0o755) << 16
        launch_script = (source / "distribution" / f"portable.{suffix}").read_text(encoding="utf-8")
        bundle.writestr(launcher, launch_script.replace("\n", "\r\n") if windows else launch_script)
        bundle.write(source / "distribution" / "portable-start.txt", "Sori/START HERE.txt")
        bundle.write(source / "LICENSE", "Sori/LICENSE.txt")
        bundle.write(source / "PRIVACY.md", "Sori/PRIVACY.md")
        bundle.write(source / "THIRD-PARTY-NOTICES.md", "Sori/THIRD-PARTY-NOTICES.md")
        add_runtime(bundle, runtime, site)
        for path in sorted(wheels.rglob("*")):
            relative = path.relative_to(wheels)
            if (
                path.is_file()
                and relative.parts[0] not in {"bin", "Scripts"}
                and not path.name.startswith(".")
            ):
                bundle.write(path, f"Sori/runtime/{site}/{relative.as_posix()}")
        for path in sorted(source.rglob("*")):
            if path.is_file():
                bundle.write(path, f"Sori/app/{path.relative_to(source).as_posix()}")
    partial.replace(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("targets", choices=tuple(TARGETS), nargs="+")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    build = root / "build"
    build.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="portable-", dir=build))
    source = stage / "source"
    public_release.snapshot(root, source)
    for target in args.targets:
        result = build_target(source, stage, args.output.resolve(), args.cache.resolve(), target)
        print(f"{sha256(result)}  {result.name}", flush=True)


if __name__ == "__main__":
    main()
