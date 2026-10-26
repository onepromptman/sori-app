#!/usr/bin/env python3
"""
settings.py — Sori's Settings pane from a shell, no window needed.

The same knobs the window's Settings tab exposes, as a command so a script or
a Claude Code / Cowork skill can set them. Every verb goes through app.Api
(the window's bridge) and the same shows.json / credentials.json, so the exe
and the CLI always agree. Honours SORI_HOME.

    python3 sori.py settings show [--json]
    python3 sori.py settings model <tiny.en|base.en|small.en|large-v3>
    python3 sori.py settings lang <auto|en|ko>          (ko needs large-v3; the engine refuses .en)
    python3 sori.py settings deck-theme <baek|dark|dancheong>
    python3 sori.py settings transcripts-dir <path>     created if missing
    python3 sori.py settings transcripts-dir --default  back to <SORI_HOME>/Transcripts
    python3 sori.py settings api-key set                reads ANTHROPIC_API_KEY from the environment
    python3 sori.py settings api-key clear | status

The API key is never accepted on the command line (argv lands in shell
history and process listings) and never printed beyond its last 4 characters.
It is stored in credentials.json, never in shows.json. Exit codes: 0 ok, 1
the engine refused (message on stderr, "!! "), 2 usage.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sys

import app

MODELS = ("tiny.en", "base.en", "small.en", "large-v3")
LANGS = ("auto", "en", "ko")
# Themes come from deck_render so a new backend shows up here for free --
# and so a checkout without the private engine/ offers only what it can render.
import deck_render  # noqa: E402

THEMES = tuple(deck_render.THEMES)


class CliError(Exception):
    """A refusal to report as `!! message` with exit 1."""


class UsageError(CliError):
    """A bad combination argparse cannot express; exit 2 like any usage error."""


def _call(method, *args):
    """Run one bridge method quietly and unwrap {ok, data|error}.

    `bridge` prints a traceback to stderr on every refusal and deck_render
    prints a warning on import; neither belongs in CLI output, so both
    streams are swallowed for the duration of the call.
    """
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        res = method(*args)
    if not res.get("ok"):
        raise CliError(res.get("error") or "unknown error")
    return res.get("data")


def _snapshot(api: app.Api) -> dict:
    base = _call(api.get_settings)
    training = _call(api.get_training_settings)
    return {
        "model": base["model"],
        "lang": base["lang"],
        "transcripts_dir": base["transcripts_dir"],
        "deck_theme": training["deck_theme"],
        "api_key_set": bool(training["has_api_key"]),
        "api_key_last4": training["api_key_last4"],
    }


def _key_line(s: dict) -> str:
    return f"set (...{s['api_key_last4']})" if s["api_key_set"] else "not set"


def _print_snapshot(s: dict) -> None:
    for label, value in (("model", s["model"]), ("lang", s["lang"]),
                         ("transcripts_dir", s["transcripts_dir"]),
                         ("deck_theme", s["deck_theme"]), ("api key", _key_line(s))):
        print(f"{label:16}{value}")


# -- verbs ------------------------------------------------------------------

def cmd_show(api: app.Api, args) -> int:
    snap = _snapshot(api)
    if args.json:
        print(json.dumps(snap, indent=2))  # ensure_ascii on: valid JSON on any console
    else:
        _print_snapshot(snap)
    return 0


def cmd_model(api: app.Api, args) -> int:
    res = _call(api.set_settings, {"model": args.model})
    print(f"model {res['model']}")
    return 0


def cmd_lang(api: app.Api, args) -> int:
    res = _call(api.set_settings, {"lang": args.lang})
    print(f"lang {res['lang']}")
    return 0


def cmd_deck_theme(api: app.Api, args) -> int:
    res = _call(api.set_training_settings, {"deck_theme": args.theme})
    print(f"deck-theme {res['deck_theme']}")
    return 0


def cmd_transcripts_dir(api: app.Api, args) -> int:
    if args.default == (args.path is not None):
        raise UsageError("transcripts-dir needs a path or --default (not both)")
    res = _call(api.set_transcripts_dir, None if args.default else args.path)
    print(f"transcripts_dir {res['transcripts_dir']}")
    return 0


def cmd_api_key(api: app.Api, args) -> int:
    action = args.action
    if action == "status":
        print(f"api key: {_key_line(_snapshot(api))}")
        return 0
    if action == "clear":
        _call(api.set_training_settings, {"api_key": ""})
        print("cleared")
        return 0
    if action == "set":
        key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        if not key:
            raise CliError("ANTHROPIC_API_KEY is not set in the environment "
                           "(the key is never taken from the command line)")
        res = _call(api.set_training_settings, {"api_key": key})
        print(f"saved (...{res['api_key_last4']})")
        return 0
    raise CliError(f"unknown api-key action {action!r}")


# -- argparse ---------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="settings.py",
                                description="Sori settings from the shell (same store as the window).")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show", help="print every setting")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("model", help="Whisper model")
    s.add_argument("model", choices=MODELS)
    s.set_defaults(fn=cmd_model)

    s = sub.add_parser("lang", help="transcription language")
    s.add_argument("lang", choices=LANGS)
    s.set_defaults(fn=cmd_lang)

    s = sub.add_parser("deck-theme", help="training deck theme")
    s.add_argument("theme", choices=THEMES)
    s.set_defaults(fn=cmd_deck_theme)

    s = sub.add_parser("transcripts-dir", help="where transcripts land")
    s.add_argument("path", nargs="?")
    s.add_argument("--default", action="store_true", help="back to <SORI_HOME>/Transcripts")
    s.set_defaults(fn=cmd_transcripts_dir)

    s = sub.add_parser("api-key", help="Claude API key (read from ANTHROPIC_API_KEY)")
    s.add_argument("action", choices=("set", "clear", "status"))
    s.set_defaults(fn=cmd_api_key)
    return p


def _tolerant_streams() -> None:
    """A piped stdout on Windows is cp1252 + strict; a Korean show name must
    not turn into a UnicodeEncodeError traceback. Escape instead."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _tolerant_streams()
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse: 2 on usage error, 0 on --help
        return int(exc.code or 0)
    try:
        return args.fn(app.Api(), args)
    except UsageError as exc:
        print(f"usage: {exc}", file=sys.stderr)
        return 2
    except CliError as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
