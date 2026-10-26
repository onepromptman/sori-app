#!/usr/bin/env python3
"""
sori.py — the one command behind the Claude-native Sori, on any OS.

    python3 sori.py doctor               what is installed, what is missing, how to fix it
    python3 sori.py setup                create Sori's own Python environment and install deps
    python3 sori.py update               upgrade yt-dlp (YouTube changes often; this is the fix)
    python3 sori.py transcribe ...       -> transcribe.py
    python3 sori.py shows ...            -> shows.py
    python3 sori.py settings ...         -> settings.py
    python3 sori.py train ...            -> train.py
    python3 sori.py sweep                -> app.py --sweep
    python3 sori.py selftest             -> app.py --selftest
    python3 sori.py app                  -> app.py (the window; Windows only in practice)

Why this file exists. The Windows exe bundles its own Python. Every other
door (the Claude Code / Cowork plugin on a Mac or Linux box, a plain shell)
used to begin with "pip install -r requirements-app.txt", which on a modern
Mac fails three different ways: the system python3 is too old, Homebrew's
python refuses `pip install` outside a venv (PEP 668), and the app profile
drags in pywebview and PyInstaller that a window-less user never needs. So
this launcher owns the environment instead:

* It keeps a private virtualenv at `<SORI_HOME>/.venv` (default `~/Sori/.venv`),
  beside the transcripts, so a plugin update never touches it and
  `SORI_HOME=<dir>` isolates it like everything else.
* It installs the smallest profile that does the job (`requirements-claude.txt`:
  yt-dlp, faster-whisper, python-pptx), plus `requirements-mac.txt`
  (mlx-whisper) on Apple Silicon for GPU-speed transcription.
* It prefers `uv` when present (fast, can fetch a Python 3.12 by itself) and
  falls back to the running interpreter's `venv` when that interpreter is
  3.11 or newer. It never pipes a download into a shell.
* Every other verb is a pass-through: the first one you run creates the
  environment if it is missing, so "python3 sori.py transcribe <url>" on a
  fresh machine just works, after a one-time install that prints what it does.

This file must stay importable and runnable on Python 3.8+, because it is
the thing that explains to a user with an old interpreter what to do next.
No f-string nesting tricks, no `X | None`, no `match`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent
MIN_PY = (3, 11)
WANT_PY = "3.12"          # what uv is asked to fetch when the host Python is too old
PROFILE_FILE = "sori-profile.json"

PROFILES = {
    # name: requirements files, in install order
    "claude": ["requirements-claude.txt"],
    "captions": ["requirements-captions.txt"],
    "app": ["requirements-app.txt"],
}
MAC_EXTRA = "requirements-mac.txt"

# Scripts the pass-through verbs run. app.py gets its flag appended.
VERBS = {
    "transcribe": ["transcribe.py"],
    "shows": ["shows.py"],
    "settings": ["settings.py"],
    "train": ["train.py"],
    "sweep": ["app.py", "--sweep"],
    "selftest": ["app.py", "--selftest"],
    "app": ["app.py"],
}


# ---------------------------------------------------------------------------
# Paths and platform facts
# ---------------------------------------------------------------------------

def state_dir() -> Path:
    """Same rule as app.state_dir(), without importing app (which needs deps)."""
    override = os.environ.get("SORI_HOME") or os.environ.get("PODCAST_STUDIO_HOME")
    return Path(override) if override else Path.home() / "Sori"


def venv_dir() -> Path:
    return state_dir() / ".venv"


def venv_python(venv: Optional[Path] = None) -> Path:
    venv = venv or venv_dir()
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def host_python_ok() -> bool:
    return sys.version_info >= MIN_PY


def uv_path() -> Optional[str]:
    return shutil.which("uv")


def requirement_files(profile: str, mac: Optional[bool] = None) -> List[str]:
    files = list(PROFILES[profile])
    if mac is None:
        mac = is_apple_silicon()
    if mac and profile == "claude":
        files.append(MAC_EXTRA)
    return files


def _fingerprint(files: List[str]) -> str:
    h = hashlib.sha256()
    for name in files:
        h.update(name.encode())
        h.update((ROOT / name).read_bytes())
    return h.hexdigest()[:16]


def _read_profile(venv: Path) -> Dict:
    try:
        return json.loads((venv / PROFILE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def env_status(profile: str = "claude") -> Dict:
    """What `doctor` reports and what `ensure_env` decides from."""
    venv = venv_dir()
    py = venv_python(venv)
    files = requirement_files(profile)
    want = _fingerprint(files)
    have = _read_profile(venv)
    return {
        "venv": str(venv),
        "venv_python": str(py),
        "exists": py.exists(),
        "profile_installed": have.get("profile"),
        "fingerprint_installed": have.get("fingerprint"),
        "fingerprint_wanted": want,
        "requirements": files,
        "current": py.exists() and have.get("profile") == profile and have.get("fingerprint") == want,
    }


# ---------------------------------------------------------------------------
# Environment creation
# ---------------------------------------------------------------------------

def _run(cmd: List[str], **kw) -> int:
    print("   $ " + " ".join(cmd))
    return subprocess.run(cmd, **kw).returncode


def create_venv(venv: Path) -> Optional[str]:
    """Make the venv. Returns None on success, else a human-readable reason."""
    venv.parent.mkdir(parents=True, exist_ok=True)
    uv = uv_path()
    if uv:
        # uv fetches a managed CPython when the host has none new enough, so
        # this is the path that works on a Mac whose only python3 is 3.9.
        if _run([uv, "venv", "--python", WANT_PY, str(venv)]) == 0:
            return None
        if host_python_ok() and _run([uv, "venv", "--python", sys.executable, str(venv)]) == 0:
            return None
        return "uv could not create the environment (see its output above)"
    if not host_python_ok():
        return ("this Python is %d.%d; Sori needs %d.%d or newer. Install uv "
                "(https://docs.astral.sh/uv/getting-started/installation/) or a "
                "current Python from https://www.python.org/downloads/, then rerun."
                % (sys.version_info[0], sys.version_info[1], MIN_PY[0], MIN_PY[1]))
    if _run([sys.executable, "-m", "venv", str(venv)]) != 0:
        return "python -m venv failed (see above)"
    return None


def install_requirements(venv: Path, files: List[str]) -> Optional[str]:
    py = venv_python(venv)
    uv = uv_path()
    for name in files:
        req = ROOT / name
        if uv:
            code = _run([uv, "pip", "install", "--python", str(py), "-r", str(req)])
        else:
            code = _run([str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-checks",
                         "-r", str(req)])
        if code != 0:
            return "installing %s failed (see above)" % name
    return None


def ensure_env(profile: str = "claude", force: bool = False) -> int:
    """Create or refresh the venv so `profile` is installed. 0 ok, else an exit code."""
    st = env_status(profile)
    venv = venv_dir()
    if st["current"] and not force:
        return 0
    if not st["exists"]:
        print("== Sori: first run, creating its Python environment at %s ==" % venv)
        reason = create_venv(venv)
        if reason:
            print("!! " + reason, file=sys.stderr)
            return 2
    else:
        print("== Sori: updating the installed profile (%s -> %s) =="
              % (st["profile_installed"] or "none", profile))
    print("== Sori: installing %s ==" % ", ".join(st["requirements"]))
    reason = install_requirements(venv, st["requirements"])
    if reason:
        print("!! " + reason, file=sys.stderr)
        return 2
    (venv / PROFILE_FILE).write_text(json.dumps({
        "profile": profile,
        "fingerprint": st["fingerprint_wanted"],
        "requirements": st["requirements"],
        "python": _venv_version(venv),
    }, indent=2), encoding="utf-8")
    print("== Sori: environment ready ==")
    return 0


def _venv_version(venv: Path) -> str:
    try:
        out = subprocess.run([str(venv_python(venv)), "-c",
                              "import sys; print('%d.%d.%d' % sys.version_info[:3])"],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "?"


# ---------------------------------------------------------------------------
# Verbs
# ---------------------------------------------------------------------------

def cmd_setup(args) -> int:
    return ensure_env(args.profile, force=args.force)


def cmd_update(args) -> int:
    """Upgrade yt-dlp inside the venv. YouTube changes its pages often enough
    that 'captions stopped working' is almost always fixed by this alone."""
    code = ensure_env(args.profile)
    if code:
        return code
    py = venv_python()
    uv = uv_path()
    if uv:
        return _run([uv, "pip", "install", "--python", str(py), "--upgrade", "yt-dlp"])
    return _run([str(py), "-m", "pip", "install", "--quiet", "--upgrade", "yt-dlp"])


def _probe_modules(py: Path, names: List[str]) -> Dict[str, Optional[str]]:
    """Import each module inside the venv; version string or None."""
    code = (
        "import importlib, json, sys\n"
        "out = {}\n"
        "for n in sys.argv[1:]:\n"
        "    try:\n"
        "        m = importlib.import_module(n)\n"
        "        out[n] = str(getattr(m, '__version__', 'ok'))\n"
        "    except Exception:\n"
        "        out[n] = None\n"
        "print(json.dumps(out))\n"
    )
    try:
        res = subprocess.run([str(py), "-c", code] + names, capture_output=True, text=True, timeout=120)
        return json.loads(res.stdout or "{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return {n: None for n in names}


def doctor_report(profile: str = "claude") -> Dict:
    st = env_status(profile)
    report = {
        "os": platform.system(),
        "arch": platform.machine(),
        "apple_silicon": is_apple_silicon(),
        "host_python": "%d.%d.%d" % sys.version_info[:3],
        "host_python_ok": host_python_ok(),
        "uv": uv_path(),
        "sori_root": str(ROOT),
        "state_dir": str(state_dir()),
        "env": st,
        "modules": {},
        "shows": None,
        "api_key": None,
        "problems": [],
        "fixes": [],
    }
    if st["exists"]:
        wanted = ["yt_dlp", "faster_whisper", "pptx"]
        if is_apple_silicon():
            wanted.append("mlx_whisper")
        report["modules"] = _probe_modules(venv_python(), wanted)
        for name, ver in report["modules"].items():
            if ver is None and name != "mlx_whisper":
                report["problems"].append("%s is not installed in the Sori environment" % name)
        if not st["current"]:
            report["problems"].append("the environment is out of date for profile '%s'" % profile)
            report["fixes"].append("python3 sori.py setup")
    else:
        report["problems"].append("Sori's Python environment does not exist yet")
        if uv_path() or host_python_ok():
            report["fixes"].append("python3 sori.py setup")
        else:
            report["fixes"].append(
                "install uv (https://docs.astral.sh/uv/getting-started/installation/) "
                "or Python %d.%d+ (https://www.python.org/downloads/), then: python3 sori.py setup"
                % MIN_PY)
    shows = state_dir() / "shows.json"
    if shows.exists():
        try:
            data = json.loads(shows.read_text(encoding="utf-8"))
            report["shows"] = len(data.get("shows") or [])
        except (OSError, ValueError):
            report["shows"] = None
    else:
        report["shows"] = 0
    # Never read the key itself here; existence of the file is all doctor says.
    report["api_key"] = "saved" if (state_dir() / "credentials.json").exists() else "not set"
    return report


def cmd_doctor(args) -> int:
    rep = doctor_report(args.profile)
    if args.json:
        print(json.dumps(rep, indent=2))
        return 1 if rep["problems"] else 0
    print("Sori doctor")
    print("  os          %s %s%s" % (rep["os"], rep["arch"], "  (Apple Silicon)" if rep["apple_silicon"] else ""))
    print("  python      %s (host)%s" % (rep["host_python"], "" if rep["host_python_ok"] else "  too old for Sori itself"))
    print("  uv          %s" % (rep["uv"] or "not found"))
    print("  sori        %s" % rep["sori_root"])
    print("  state       %s  (%s show(s), api key %s)" % (rep["state_dir"], rep["shows"], rep["api_key"]))
    env = rep["env"]
    if env["exists"]:
        print("  env         %s  (profile %s%s)" % (env["venv"], env["profile_installed"] or "?",
                                                      "" if env["current"] else ", needs setup"))
        for name, ver in rep["modules"].items():
            print("    %-16s %s" % (name, ver or "MISSING"))
    else:
        print("  env         %s  (not created yet)" % env["venv"])
    if rep["problems"]:
        print("problems:")
        for p in rep["problems"]:
            print("  - " + p)
        print("fix:")
        for f in rep["fixes"]:
            print("  " + f)
        return 1
    print("ok: ready to transcribe.")
    return 0


def cmd_passthrough(verb: str, rest: List[str], profile: str) -> int:
    code = ensure_env(profile)
    if code:
        return code
    cmd = [str(venv_python())] + [str(ROOT / VERBS[verb][0])] + VERBS[verb][1:] + rest
    env = dict(os.environ)
    env["SORI_PROFILE"] = profile          # app.py --selftest reads it
    try:
        return subprocess.run(cmd, cwd=str(ROOT), env=env).returncode
    except KeyboardInterrupt:
        return 130


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sori.py", description="Sori on any OS: one launcher, its own Python environment.")
    p.add_argument("--profile", choices=sorted(PROFILES), default="claude",
                   help="dependency profile (default: claude = transcripts + decks, no window)")
    sub = p.add_subparsers(dest="verb", required=True)
    s = sub.add_parser("setup", help="create or refresh Sori's Python environment")
    s.add_argument("--force", action="store_true", help="reinstall even if up to date")
    sub.add_parser("doctor", help="report what is installed and how to fix what is not").add_argument(
        "--json", action="store_true")
    sub.add_parser("update", help="upgrade yt-dlp (fixes most 'YouTube stopped working' cases)")
    for verb in VERBS:
        sub.add_parser(verb, help="run %s" % " ".join(VERBS[verb]), add_help=False)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Pass-through verbs keep their own flags: split before argparse sees them.
    profile = "claude"
    if len(argv) >= 2 and argv[0] == "--profile" and argv[1] in PROFILES:
        profile, argv = argv[1], argv[2:]
    if argv and argv[0] in VERBS:
        return cmd_passthrough(argv[0], argv[1:], profile)
    p = build_parser()
    args = p.parse_args((["--profile", profile] if profile != "claude" else []) + argv)
    if args.verb == "setup":
        return cmd_setup(args)
    if args.verb == "doctor":
        return cmd_doctor(args)
    if args.verb == "update":
        return cmd_update(args)
    p.error("unknown verb")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
