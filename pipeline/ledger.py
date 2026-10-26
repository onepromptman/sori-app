"""
ledger.py — the per-episode record of what the pipeline did.

`<SORI_HOME>/ledger.jsonl`, one JSON object per line, append-only:

    {"at": "2026-10-27T09:04:11Z", "show": "Lex Fridman", "episode_id": "yt:abc",
     "title": "#502 ...", "stage": "briefed", "by": "ld-architect",
     "artifact": "Trainings/Lex Fridman/2026-10-26 - #502/brief.md", "note": ""}

Why JSONL and not a column in shows.json: shows.json is the engine's live
store and is rewritten under a lock by the window, the poller and the sweep;
a ledger that only ever appends cannot clobber it and survives a corrupt
store. Why not sweep.log: that is prose for humans; this is data for the
curate skill ("which transcripts have no brief yet") and for `sori.py ledger`.

Stages are ordered. `latest()` keeps the furthest stage per episode, so a
`skipped` or `failed` row after `transcribed` is the state, and a later
`briefed` row moves it on again.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

STAGES = [
    "discovered",     # the sweep or the window saw a new episode
    "transcribed",    # a transcript .txt exists
    "triaged",        # curator decided train / skip / park (triage.json)
    "briefed",        # ld-architect wrote brief.md
    "critiqued",      # training-critic wrote critique.md with PASS or REVISE
    "outlined",       # outline.json exists (offline backend)
    "rendered",       # a .pptx + study guide exist (offline backend)
    "designed",       # an external design tool holds the deck (link in artifact)
    "reviewed",       # the owner looked at it
    "skipped",        # curator: not worth a training (note says why)
    "failed",         # a stage raised; note carries the reason
]
_RANK = {s: i for i, s in enumerate(STAGES)}
TERMINAL = {"skipped", "failed"}


def state_dir() -> Path:
    override = os.environ.get("SORI_HOME") or os.environ.get("PODCAST_STUDIO_HOME")
    root = Path(override) if override else Path.home() / "Sori"
    root.mkdir(parents=True, exist_ok=True)
    return root


def ledger_path() -> Path:
    return state_dir() / "ledger.jsonl"


def _safe(text: str, limit: int = 90) -> str:
    """Same shape as app._safe_name: a folder name that works on every OS."""
    # Also strip `$` and backticks: these names end up inside shell snippets
    # in hand-off READMEs, and a feed title is untrusted input.
    cleaned = re.sub(r'[<>:"/\\|?*$`\x00-\x1f]+', " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:limit].rstrip(". ") or "untitled"


def episode_dir(show_name: str, episode: dict, trainings_root: Path | None = None) -> Path:
    """`Trainings/<Show>/<date> - <title>/`: every artifact of one episode in
    one folder (transcript copy, triage.json, brief.md, critique.md,
    outline.json, deck, handoff/). Created on first use."""
    root = trainings_root or (state_dir() / "Trainings")
    date = (episode.get("date") or "").strip()
    name = f"{date} - {episode.get('title', '')}" if date else (episode.get("title") or "")
    d = root / _safe(show_name) / _safe(name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def record(show: str, episode_id: str, stage: str, by: str, title: str = "",
           artifact: str | Path | None = None, note: str = "") -> dict:
    """Append one row. Unknown stages are refused so the ledger stays queryable."""
    if stage not in _RANK:
        raise ValueError(f"unknown stage {stage!r}; one of {', '.join(STAGES)}")
    row = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "show": show, "episode_id": episode_id, "title": title, "stage": stage, "by": by,
        "artifact": _relative(artifact), "note": note or "",
    }
    path = ledger_path()
    # A crash mid-write can leave a torn last line with no newline; appending
    # straight after it would glue two rows together and lose both. Start
    # this row on its own line whatever the file ends with.
    prefix = ""
    try:
        if path.exists() and path.stat().st_size and not path.read_bytes().endswith(b"\n"):
            prefix = "\n"
    except OSError:
        pass
    with open(path, "a", encoding="utf-8") as f:
        f.write(prefix + json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _relative(artifact) -> str:
    if artifact is None:
        return ""
    p = Path(artifact)
    try:
        return str(p.resolve().relative_to(state_dir().resolve()))
    except (ValueError, OSError):
        return str(p)


def rows(since_days: int | None = None) -> list[dict]:
    path = ledger_path()
    if not path.exists():
        return []
    out: list[dict] = []
    cutoff = None
    if since_days is not None:
        cutoff = datetime.now(timezone.utc).timestamp() - since_days * 86400
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue           # a torn line never breaks the whole ledger
        if cutoff is not None:
            try:
                at = datetime.fromisoformat(row["at"].replace("Z", "+00:00")).timestamp()
            except (KeyError, ValueError):
                at = 0
            if at < cutoff:
                continue
        out.append(row)
    return out


def latest(since_days: int | None = None) -> dict[str, dict]:
    """episode_id -> its current state: the row with the highest-ranked stage,
    ties broken by time. A terminal row (skipped/failed) wins over anything
    earlier than itself but loses to a later, further stage."""
    current: dict[str, dict] = {}
    for row in rows(since_days):
        eid = row.get("episode_id")
        if not eid or row.get("stage") not in _RANK:
            continue
        prev = current.get(eid)
        if prev is None or _RANK[row["stage"]] >= _RANK[prev["stage"]]:
            current[eid] = row
    return current


def awaiting(stage_done: str, stage_next: str, since_days: int | None = None) -> list[dict]:
    """Episodes whose current stage is exactly `stage_done` (so `stage_next`
    has not happened). The curate skill asks for awaiting('transcribed',
    'triaged') and awaiting('briefed', 'critiqued')."""
    return [r for r in latest(since_days).values() if r["stage"] == stage_done]


def summary(since_days: int | None = None) -> dict[str, int]:
    counts = {s: 0 for s in STAGES}
    for row in latest(since_days).values():
        counts[row["stage"]] += 1
    return counts
