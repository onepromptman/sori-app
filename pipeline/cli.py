#!/usr/bin/env python3
"""
pipeline/cli.py — the pipeline verbs sori.py routes here (run inside Sori's venv).

    python3 sori.py ledger [--days N] [--json]            per-episode state table
    python3 sori.py ledger add <episode_id> <stage> <by> [--show S] [--title T] [--artifact P] [--note N]
    python3 sori.py curate --list [--days N]              transcripts with no triage yet, as JSON
    python3 sori.py curate --init                         write ~/Sori/curriculum.md from the template
    python3 sori.py brief-check <brief.md> <transcript.txt>
    python3 sori.py brief-template "<title>" [--show S --date D --source U]
    python3 sori.py design <episode-dir> [--backend B]    write handoff/<backend>/ (offline also renders)
    python3 sori.py design-config [key value]             pipeline.json settings

Exit codes follow the other CLIs: 0 ok, 1 refused (`!! ...` on stderr), 2 usage.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline import brief as briefmod  # noqa: E402
from pipeline import design, ledger  # noqa: E402

CURRICULUM_TEMPLATE = ROOT / "docs" / "curriculum.template.md"


def _refuse(msg: str) -> int:
    print(f"!! {msg}", file=sys.stderr)
    return 1


def cmd_ledger(args) -> int:
    if args.sub == "add":
        row = ledger.record(args.show or "", args.episode_id, args.stage, args.by, title=args.title or "",
                            artifact=args.artifact, note=args.note or "")
        print(json.dumps(row, ensure_ascii=False) if args.json else f"recorded {row['stage']} for {row['episode_id']}")
        return 0
    current = ledger.latest(args.days)
    if args.json:
        print(json.dumps({"episodes": list(current.values()), "summary": ledger.summary(args.days)}, indent=2,
                         ensure_ascii=False))
        return 0
    if not current:
        print("ledger is empty. The sweep writes `transcribed` rows; /sori:curate writes the rest.")
        return 0
    rows = sorted(current.values(), key=lambda r: (r.get("show", ""), r.get("at", "")))
    widths = [max(len(str(r.get(k, ""))) for r in rows + [{"show": "show", "title": "title", "stage": "stage",
                                                           "by": "by", "at": "at"}])
              for k in ("show", "title", "stage", "by", "at")]
    fmt = "  ".join("{:<%d}" % min(w, 48) for w in widths)
    print(fmt.format("show", "title", "stage", "by", "at"))
    for r in rows:
        print(fmt.format(*(str(r.get(k, ""))[:48] for k in ("show", "title", "stage", "by", "at"))))
    s = ledger.summary(args.days)
    print("\n" + ", ".join(f"{k} {v}" for k, v in s.items() if v))
    return 0


def cmd_curate(args) -> int:
    if args.init:
        dest = ledger.state_dir() / "curriculum.md"
        if dest.exists() and not args.force:
            return _refuse(f"{dest} exists; pass --force to overwrite")
        shutil.copy2(CURRICULUM_TEMPLATE, dest)
        print(f"wrote {dest}; edit it, then run /sori:curate")
        return 0
    todo = ledger.awaiting("transcribed", "triaged", args.days)
    briefed = ledger.awaiting("briefed", "critiqued", args.days)
    curriculum = ledger.state_dir() / "curriculum.md"
    out = {
        "curriculum": str(curriculum) if curriculum.exists() else None,
        "awaiting_triage": todo,
        "awaiting_critique": briefed,
        "trainings_root": str(ledger.state_dir() / "Trainings"),
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_brief_check(args) -> int:
    b, t = Path(args.brief), Path(args.transcript)
    if not b.is_file():
        return _refuse(f"brief not found: {b}")
    if not t.is_file():
        return _refuse(f"transcript not found: {t}")
    report = briefmod.check_files(b, t)
    print(report)
    return 0 if report.ok else 1


def cmd_brief_template(args) -> int:
    print(briefmod.TEMPLATE.format(title=args.title, show=args.show or "", date=args.date or "",
                                   source=args.source or ""))
    return 0


def cmd_design(args) -> int:
    ep_dir = Path(args.episode_dir)
    if not ep_dir.is_dir():
        return _refuse(f"episode folder not found: {ep_dir}")
    cfg = design.load_config()
    backend = args.backend or cfg["design_backend"]
    try:
        out = design.handoff(ep_dir, backend, cfg)
    except design.HandoffError as exc:
        return _refuse(str(exc))
    print(f"handoff: {out}")
    if backend == "offline":
        outline = ep_dir / "outline.json"
        transcript = design.find_transcript(ep_dir)
        if outline.exists() and transcript is not None:
            import train
            code = train.main([str(transcript), "--outline", str(outline), "--out", str(ep_dir)])
            if code:
                return code
            decks = sorted(ep_dir.glob("*.pptx"))
            if decks and args.episode_id:
                ledger.record(args.show or ep_dir.parent.name, args.episode_id, "rendered", "sori.py design",
                              title=ep_dir.name, artifact=decks[-1])
        else:
            print("no outline.json yet: follow handoff/offline/README.md to write one, then rerun.")
    return 0


def cmd_design_config(args) -> int:
    if args.key is None:
        print(json.dumps(design.load_config(), indent=2))
        return 0
    if args.value is None:
        return _refuse("design-config needs `<key> <value>` or no arguments")
    try:
        cfg = design.save_config({args.key: args.value})
    except ValueError as exc:
        return _refuse(str(exc))
    print(json.dumps(cfg, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sori.py", description="Sori pipeline verbs")
    sub = p.add_subparsers(dest="verb", required=True)

    pl = sub.add_parser("ledger")
    pl.add_argument("--days", type=int)
    pl.add_argument("--json", action="store_true")
    lsub = pl.add_subparsers(dest="sub")
    la = lsub.add_parser("add")
    la.add_argument("episode_id")
    la.add_argument("stage", choices=ledger.STAGES)
    la.add_argument("by")
    la.add_argument("--show")
    la.add_argument("--title")
    la.add_argument("--artifact")
    la.add_argument("--note")
    la.add_argument("--json", action="store_true")
    pl.set_defaults(func=cmd_ledger)

    pc = sub.add_parser("curate")
    pc.add_argument("--list", action="store_true")
    pc.add_argument("--init", action="store_true")
    pc.add_argument("--force", action="store_true")
    pc.add_argument("--days", type=int)
    pc.set_defaults(func=cmd_curate)

    pb = sub.add_parser("brief-check")
    pb.add_argument("brief")
    pb.add_argument("transcript")
    pb.set_defaults(func=cmd_brief_check)

    pt = sub.add_parser("brief-template")
    pt.add_argument("title")
    pt.add_argument("--show")
    pt.add_argument("--date")
    pt.add_argument("--source")
    pt.set_defaults(func=cmd_brief_template)

    pd = sub.add_parser("design")
    pd.add_argument("episode_dir")
    pd.add_argument("--backend", choices=design.BACKENDS)
    pd.add_argument("--episode-id")
    pd.add_argument("--show")
    pd.set_defaults(func=cmd_design)

    pg = sub.add_parser("design-config")
    pg.add_argument("key", nargs="?")
    pg.add_argument("value", nargs="?")
    pg.set_defaults(func=cmd_design_config)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
