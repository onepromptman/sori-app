#!/usr/bin/env python3
"""
preflight.py: get Sori ready to run, then say which Python to run it with.

Every Sori skill runs this first:

    python preflight.py transcribe      (or: shows, sweep, train)

It checks the Python version, keeps one private environment for Sori's
packages, installs only what that verb needs at the exact versions in
pyproject.toml (and requirements.lock for what those pull in), and prints `SORI_PY=<path>` as its last line. The skill then
runs the Sori scripts with that interpreter. A second run finds everything in
place and returns at once without touching the network.

The environment lives in `${CLAUDE_PLUGIN_DATA}/venv` when Claude provides
that folder, otherwise in `venv` inside the Sori folder (`%USERPROFILE%\\Sori`,
or `SORI_HOME`).

Standard library only, and written to start on an old Python too, so that the
"your Python is too old" message can be printed by the Python that is too old.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON_FLOOR = (3, 11)
LOCK = ROOT / "requirements.lock"
MARKER = "sori-preflight.json"
LOG_NAME = "preflight.log"

# What each skill imports. Versions are not written here: they come from
# pyproject.toml, the one place Sori's pins live.
NEEDS = {
    "transcribe": ("yt-dlp", "faster-whisper"),
    "shows": ("yt-dlp", "python-pptx"),
    "sweep": ("yt-dlp", "faster-whisper", "python-pptx", "anthropic"),
    "train": ("python-pptx",),
}
# The paid route of /sori:train (`preflight.py train --api`).
API_EXTRA = ("anthropic",)
# Verbs that may fetch from YouTube, and verbs that may run Whisper.
YOUTUBE_VERBS = {"transcribe", "shows", "sweep"}
WHISPER_VERBS = {"transcribe", "sweep"}

REFUSED = (
    "Sori could not download its packages because this environment blocks package installs. "
    "Allow network access to package managers (pypi.org) for code execution in your Claude "
    "settings and start a new chat, or run Sori from Claude Code on your own computer."
)
# Text pip prints when the network, not the package, is the problem.
_NETWORK_SIGNS = (
    "connection",
    "proxy",
    "timed out",
    "temporary failure",
    "name resolution",
    "getaddrinfo",
    "403",
    "407",
    "could not find a version",
    "no matching distribution",
    "ssl",
)


class NotReady(Exception):
    """Preflight cannot finish; the message is the one line the user sees."""


def say(message: str) -> None:
    print(f"sori: {message}", flush=True)


def sori_home() -> Path:
    """The Sori folder, exactly as the app finds it (and adopts an older one)."""
    import app  # standard library at import time

    return app.state_dir()


def venv_dir() -> Path:
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    return (Path(data) if data else sori_home()) / "venv"


def venv_python(venv: Path) -> Path:
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def pins() -> dict[str, str]:
    """Every exact pin in pyproject.toml, by package name."""
    import tomllib  # Python 3.11+, which check_python() has already required

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    requirements = list(project["dependencies"])
    for group in project["optional-dependencies"].values():
        requirements += group
    return dict(requirement.split("==") for requirement in requirements)


def wanted(verb: str, api: bool = False) -> dict[str, str]:
    names = NEEDS[verb] + (API_EXTRA if api else ())
    every = pins()
    return {name: every[name] for name in names}


def check_python(version: tuple = sys.version_info) -> None:
    if tuple(version[:2]) < PYTHON_FLOOR:
        floor = ".".join(str(n) for n in PYTHON_FLOOR)
        raise NotReady(
            f"Sori needs Python {floor} or newer and this is Python {version[0]}.{version[1]}. "
            f"Install Python {floor} or newer from python.org, then run this again with it."
        )


def installed(venv: Path) -> dict[str, str]:
    """The pins a finished preflight recorded for this environment."""
    if not venv_python(venv).is_file():
        return {}
    try:
        return dict(json.loads((venv / MARKER).read_text(encoding="utf-8"))["pins"])
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def _run(command: list[str], log: Path) -> tuple[int, str]:
    """Run quietly; the full output goes to the log, never to the screen."""
    done = subprocess.run(command, capture_output=True, text=True, errors="replace")  # noqa: S603
    output = (done.stdout or "") + (done.stderr or "")
    try:
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"$ {' '.join(command)}\n{output}\n")
    except OSError:
        pass
    return done.returncode, output


def ensure(verb: str, api: bool = False) -> Path:
    """Make the environment ready for `verb` and return its interpreter."""
    check_python()
    venv = venv_dir()
    python = venv_python(venv)
    need = wanted(verb, api)
    have = installed(venv)
    missing = {name: version for name, version in need.items() if have.get(name) != version}
    if not missing:
        return python

    venv.parent.mkdir(parents=True, exist_ok=True)
    log = venv.parent / LOG_NAME
    if not python.is_file():
        say(f"setting up Sori's own Python environment in {venv} (one time)")
        code, _ = _run([sys.executable, "-m", "venv", str(venv)], log)
        if code or not python.is_file():
            raise NotReady(
                f"Sori could not create its Python environment in {venv}. "
                f"Check that the folder is writable; details are in {log}."
            )

    listing = ", ".join(f"{name} {version}" for name, version in missing.items())
    size = "about 350 MB on disk" if "faster-whisper" in missing else "a few MB"
    say(f"installing {listing} ({size}, one time; this can take a few minutes)")
    command = [str(python), "-m", "pip", "install", "--disable-pip-version-check", "--quiet"]
    command += [f"{name}=={version}" for name, version in missing.items()]
    # The lock pins what those packages pull in. Left to float, a newer
    # release of one of them (av, under faster-whisper) breaks transcription.
    if LOCK.is_file():
        command += ["--constraint", str(LOCK)]
    code, output = _run(command, log)
    if code:
        if any(sign in output.lower() for sign in _NETWORK_SIGNS):
            raise NotReady(REFUSED)
        raise NotReady(f"Sori could not install {listing}. The reason is in {log}.")

    have.update(missing)
    (venv / MARKER).write_text(json.dumps({"pins": have}, indent=2) + "\n", encoding="utf-8")
    return python


def notices(verb: str, model: str) -> list[str]:
    """Things worth saying before the first run: downloads and missing helpers."""
    out = []
    if verb in WHISPER_VERBS:
        import transcribe  # standard library at import time

        if not transcribe.whisper_model_is_cached(model):
            out.append(
                f"the first audio transcription will download the Whisper model {model} "
                "(about 150 MB for base.en, more for larger models), once. "
                "YouTube captions need no model."
            )
    if verb in YOUTUBE_VERBS and not shutil.which("deno"):
        out.append(
            "no JavaScript runtime (Deno) was found. yt-dlp needs one for some YouTube "
            "videos; if a YouTube step fails, install Deno from https://deno.com and try again. "
            "Podcast feeds and audio files do not need it."
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="preflight.py", description="Get Sori ready to run and print the Python to run it with."
    )
    parser.add_argument("verb", choices=sorted(NEEDS))
    parser.add_argument(
        "--api", action="store_true", help="also install what the paid Claude API route needs"
    )
    parser.add_argument(
        "--model", default="base.en", help="Whisper model the run will use (default: base.en)"
    )
    args = parser.parse_args(argv)
    try:
        python = ensure(args.verb, args.api)
    except NotReady as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 2
    for notice in notices(args.verb, args.model):
        say(f"note: {notice}")
    say("ready")
    print(f"SORI_PY={python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
