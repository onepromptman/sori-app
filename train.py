#!/usr/bin/env python3
"""
train.py — turn one transcript into a training deck (.pptx) + study guide (.md).

The same step the Sori window runs from its Training button, exposed as a
command so it can be driven from a shell, a script, or a Claude Code / Cowork
skill. This is the one part of Sori that is NOT free: it makes a single
Claude API call, which costs money per run. Everything it needs is already in
training.py (the call) and deck_render.py (the pptx); this file only parses
arguments, finds a key, and writes the two files.

    py train.py "Transcripts/The Daily/2026-09-04 - Some Episode.txt"
    py train.py transcript.txt --out ./Trainings --theme dark
    py train.py transcript.txt --title "Ep. 12" --show "My Show" --date 2026-09-05

Claude-native route (no API key, no spend): the Claude Code session writes the
outline itself, then this renders it. Same rules, same schema, same renderer.

    py train.py --brief                              # print the rules + JSON schema
    py train.py transcript.txt --outline outline.json --theme baek

Key lookup (API route only): ANTHROPIC_API_KEY in the environment, then the key
saved by the Sori app or `settings.py api-key set`
(%USERPROFILE%/Sori/credentials.json; SORI_HOME overrides). A key is never
accepted on the command line (argv lands in shell history and process
listings) and never printed.

Transcripts written by Sori start with three header lines (title, "show —
date", source URL); those are read for the deck metadata when --title/--show/
--date are not given. Any other .txt works too, it just gets an empty header.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import sori_log
import training as tr

# Derived, not hardcoded: a checkout without the private engine/ offers only
# the themes it can actually render (see themes/README.md).
import deck_render  # noqa: E402

THEMES = tuple(deck_render.THEMES)


def _sori_key() -> str | None:
    home = os.environ.get("SORI_HOME") or os.environ.get("PODCAST_STUDIO_HOME")
    root = Path(home) if home else Path.home() / "Sori"
    try:
        data = json.loads((root / "credentials.json").read_text(encoding="utf-8"))
        return (data.get("anthropic_api_key") or "").strip() or None
    except (OSError, ValueError):
        return None


def _header_meta(text: str) -> dict:
    """Best-effort read of Sori's 3-line transcript header."""
    lines = text.splitlines()
    meta = {"title": "", "show": "", "date": ""}
    if len(lines) >= 2:
        meta["title"] = lines[0].strip()
        m = re.match(r"^(.*?)\s+[—-]\s+(\d{4}-\d{2}-\d{2})\s*$", lines[1].strip())
        if m:
            meta["show"], meta["date"] = m.group(1).strip(), m.group(2)
    return meta


def _safe(name: str, limit: int = 80) -> str:
    return re.sub(r'[<>:"/\|?*\x00-\x1f]+', " ", name).strip(" .")[:limit] or "training"


def main(argv: list[str] | None = None) -> int:
    sori_log.setup()
    p = argparse.ArgumentParser(
        prog="train.py",
        description="Transcript -> training deck (.pptx) + study guide (.md). Costs one Claude API call.",
    )
    p.add_argument("transcript", nargs="?", help="path to a transcript .txt")
    p.add_argument(
        "--outline",
        help="render this outline JSON (written by a Claude Code session "
        "per --brief) instead of calling the Claude API; no key needed",
    )
    p.add_argument(
        "--brief",
        action="store_true",
        help="print the authoring rules and outline schema for --outline, then exit",
    )
    p.add_argument("--out", help="output folder (default: next to the transcript)")
    p.add_argument(
        "--theme",
        choices=THEMES,
        default=deck_render.DEFAULT_THEME,
        help=f"deck theme (default: {deck_render.DEFAULT_THEME})",
    )
    p.add_argument("--model", default=tr.DEFAULT_MODEL, help=f"Claude model (default: {tr.DEFAULT_MODEL})")
    p.add_argument("--title", help="override the transcript header title")
    p.add_argument("--show", help="override the show name")
    p.add_argument("--date", help="override the date (YYYY-MM-DD)")
    # parse_known_args, not parse_args: argparse's own usage error echoes
    # every unrecognized token, and a key pasted after a stray --api-key
    # must not land on stderr either. Flag names are shown, values are not.
    args, extras = p.parse_known_args(argv)
    if extras:
        shown = " ".join(a if a.startswith("-") else "<value>" for a in extras)
        print(
            f"!! unrecognized arguments: {shown}\n"
            "   (a key is never taken from the command line; set ANTHROPIC_API_KEY "
            "or save one with `settings.py api-key set`)",
            file=sys.stderr,
        )
        return 2

    if args.brief:
        print(tr.outline_brief())
        return 0
    if not args.transcript:
        p.error("transcript is required unless --brief is given")

    src = Path(args.transcript)
    if not src.is_file():
        print(f"!! transcript not found: {src}", file=sys.stderr)
        return 2
    text = src.read_text(encoding="utf-8", errors="replace")

    meta = _header_meta(text)
    for k in ("title", "show", "date"):
        if getattr(args, k):
            meta[k] = getattr(args, k)
    if not meta["title"]:
        meta["title"] = src.stem

    outline_src: dict | None = None
    if args.outline:
        try:
            outline_src = json.loads(Path(args.outline).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"!! couldn't read outline {args.outline}: {exc}", file=sys.stderr)
            return 2

    key = None if outline_src is not None else (os.environ.get("ANTHROPIC_API_KEY") or _sori_key())
    if outline_src is None and not key:
        print(
            "!! no Claude API key: set ANTHROPIC_API_KEY, or save one with "
            "`settings.py api-key set` (or Sori's Settings).",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out) if args.out else src.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / _safe(f"{meta['date'] + ' - ' if meta['date'] else ''}{meta['title']}")
    # Not with_suffix(): a title like "Ep. 12" would be cut at its last dot.
    pptx_path, md_path = base.with_name(base.name + ".pptx"), base.with_name(base.name + ".md")

    try:
        if outline_src is not None:
            print(f"rendering training for: {meta['title']!r}  (from {args.outline}, no API call)")
            result = tr.result_from_outline(outline_src, meta)
        else:
            print(f"generating training for: {meta['title']!r}  (model {args.model}, one paid API call)")
            result = tr.generate_training(text, meta, key, model=args.model)
    except tr.TrainingGenerationError as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 1

    deck_render.render_pptx(result.outline, args.theme, pptx_path)
    md_path.write_text(result.study_guide_md, encoding="utf-8")
    print(f"deck : {pptx_path}")
    print(f"guide: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
