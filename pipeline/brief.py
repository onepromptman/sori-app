"""
brief.py — the contract between the L&D agent and whoever renders the deck.

A brief is Markdown with fixed H2 sections. It is the one artifact every
design backend consumes (offline pptx, Claude Design, ChatSlide, Figma),
so it carries everything a slide needs and nothing about how a slide looks.

    # Brief: <episode title>
    show: <show>            date: YYYY-MM-DD        source: <url>
    ## Objectives            3 to 5 "After this session a <role> can ..." lines
    ## Audience              one paragraph: who, what they already know
    ## DO step               the hands-on exercise and the artifact it produces
    ## Evidence              bullets, each a verbatim quote from the transcript:
                             - [12:04] "exact words from the transcript" — why it matters
    ## Leave out             what the episode said that this training does not use
    ## Slide recommendation  a numbered list, one line per slide, kind in brackets:
                             1. [divider] ...   2. [content] ...   3. [quote] ...

The sourcing gate lives here, not in the renderer: `check()` confirms every
Evidence quote appears verbatim in the transcript (whitespace and curly
quotes normalised, nothing else) and that the structural minimums hold.
The training-critic runs it, `sori.py brief-check` runs it, and a render
backend refuses a brief that fails it. A quote the transcript does not
contain is the one fabrication this pipeline cannot allow through.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED = ["Objectives", "Audience", "DO step", "Evidence", "Leave out", "Slide recommendation"]
MIN_OBJECTIVES, MAX_OBJECTIVES = 2, 6
MIN_EVIDENCE = 3
MIN_SLIDES, MAX_SLIDES = 6, 24
# The kinds a slide line may name. Superset of training.SLIDE_KINDS so a
# brief can ask for a cover/closing explicitly and name d_sign-only layouts.
SLIDE_KINDS = {"cover", "closing", "divider", "content", "content_stat", "two_column", "process",
               "agenda", "quote", "callout", "full_bleed", "data", "scorecard", "chart",
               "manifesto", "timeline", "steps", "compare", "code", "stat", "exercise"}

_H2 = re.compile(r"^##\s+(.+?)\s*$", re.M)
_QUOTE = re.compile(r'[“"](.+?)[”"]')
_SLIDE_LINE = re.compile(r"^\s*\d+\.\s*\[([a-z_\-]+)\]\s*(.*)$")
_META = re.compile(r"^(show|date|source):\s*(.*)$", re.I)


@dataclass
class Brief:
    title: str
    meta: dict
    sections: dict          # section name -> body text
    objectives: list[str]
    evidence: list[dict]    # {"stamp", "quote", "why", "raw"}
    slides: list[dict]      # {"n", "kind", "text"}


@dataclass
class Report:
    ok: bool
    findings: list[str] = field(default_factory=list)
    checked_quotes: int = 0

    def __str__(self) -> str:
        head = "brief: PASS" if self.ok else "brief: FAIL"
        lines = [head, f"  quotes checked: {self.checked_quotes}"]
        lines += [f"  - {f}" for f in self.findings]
        return "\n".join(lines)


def parse(text: str) -> Brief:
    title = ""
    m = re.search(r"^#\s+Brief:\s*(.+?)\s*$", text, re.M)
    if m:
        title = m.group(1).strip()
    meta: dict = {}
    for line in text.splitlines():
        for part in re.split(r"\s{2,}|\t", line.strip()):
            mm = _META.match(part.strip())
            if mm:
                meta[mm.group(1).lower()] = mm.group(2).strip()
    heads = list(_H2.finditer(text))
    sections: dict = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        sections[_norm_head(h.group(1))] = text[h.end():end].strip()

    objectives = _bullets(sections.get("Objectives", ""))
    evidence = []
    for raw in _bullets(sections.get("Evidence", "")):
        stamp = re.match(r"^\[([^\]]+)\]\s*", raw)
        q = _QUOTE.search(raw)
        why = raw.split("—", 1)[1].strip() if "—" in raw else ""
        evidence.append({"stamp": stamp.group(1) if stamp else "", "quote": q.group(1).strip() if q else "",
                         "why": why, "raw": raw})
    slides = []
    for line in sections.get("Slide recommendation", "").splitlines():
        sm = _SLIDE_LINE.match(line)
        if sm:
            slides.append({"n": len(slides) + 1, "kind": sm.group(1), "text": sm.group(2).strip()})
    return Brief(title=title, meta=meta, sections=sections, objectives=objectives,
                 evidence=evidence, slides=slides)


def _norm_head(h: str) -> str:
    h = h.strip().rstrip(":")
    for name in REQUIRED:
        if h.lower() == name.lower():
            return name
    return h


def _bullets(body: str) -> list[str]:
    """Bullets, with wrapped continuation lines folded back into their bullet
    (an author who hard-wraps at 80 columns must not lose half a quote)."""
    out: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"^([-*•]|\d+\.)\s+", s):
            out.append(re.sub(r"^([-*•]|\d+\.)\s+", "", s))
        elif out:
            out[-1] = out[-1] + " " + s
    return out


def normalise(text: str) -> str:
    """Whitespace runs to one space; curly quotes and dashes to ASCII; lowercase.
    Deliberately nothing else: a paraphrase must NOT pass as a quote."""
    t = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    t = t.replace("—", "-").replace("–", "-").replace("…", "...")
    t = re.sub(r"\s+", " ", t)
    return t.strip().lower()


def check(brief_text: str, transcript_text: str) -> Report:
    """The gate. Structural minimums plus every quote verbatim in the transcript."""
    b = parse(brief_text)
    findings: list[str] = []
    if not b.title:
        findings.append("missing title line: `# Brief: <episode title>`")
    for name in REQUIRED:
        if name not in b.sections or not b.sections[name].strip():
            findings.append(f"missing or empty section: ## {name}")
    if not MIN_OBJECTIVES <= len(b.objectives) <= MAX_OBJECTIVES:
        findings.append(f"{len(b.objectives)} objectives; want {MIN_OBJECTIVES} to {MAX_OBJECTIVES} bullets")
    do = b.sections.get("DO step", "")
    if do and not re.search(r"\b(artifact|produce|write|build|draft|fill|leave with|output)\b", do, re.I):
        findings.append("DO step names no artifact the learner leaves with")
    if len(b.evidence) < MIN_EVIDENCE:
        findings.append(f"{len(b.evidence)} evidence bullets; want at least {MIN_EVIDENCE}")

    hay = normalise(transcript_text)
    checked = 0
    for i, ev in enumerate(b.evidence, 1):
        if not ev["quote"]:
            findings.append(f'evidence {i} has no quoted text: {ev["raw"][:60]!r}')
            continue
        checked += 1
        if normalise(ev["quote"]) not in hay:
            findings.append(f'evidence {i} is not verbatim in the transcript: "{ev["quote"][:70]}"')
        if not ev["stamp"]:
            findings.append(f"evidence {i} has no [timestamp]")

    if not MIN_SLIDES <= len(b.slides) <= MAX_SLIDES:
        findings.append(f"{len(b.slides)} slide lines; want {MIN_SLIDES} to {MAX_SLIDES} numbered `[kind] ...` lines")
    for sl in b.slides:
        if sl["kind"] not in SLIDE_KINDS:
            findings.append(f"slide {sl['n']} kind {sl['kind']!r} is not one of {', '.join(sorted(SLIDE_KINDS))}")
    kinds = [s["kind"] for s in b.slides]
    if kinds and not any(k in ("exercise", "scorecard", "process", "steps") for k in kinds):
        findings.append("no slide carries the DO step (exercise/scorecard/process/steps)")

    return Report(ok=not findings, findings=findings, checked_quotes=checked)


def check_files(brief_path: Path, transcript_path: Path) -> Report:
    return check(brief_path.read_text(encoding="utf-8", errors="replace"),
                 transcript_path.read_text(encoding="utf-8", errors="replace"))


TEMPLATE = """# Brief: {title}
show: {show}    date: {date}    source: {source}

## Objectives
- After this session a <role> can <observable action> ...
- ...

## Audience
Who sits in the room, what they already know, what they will not tolerate.

## DO step
The exercise, in one paragraph: what they do for 10 minutes, with what, and
the artifact they leave with. The artifact is the assessment.

## Evidence
- [mm:ss] "exact words from the transcript" — why this line earns a slide
- [mm:ss] "..." — ...
- [mm:ss] "..." — ...

## Leave out
What the episode spent time on that this training does not use, and why.

## Slide recommendation
1. [cover] <title>
2. [agenda] ...
3. [content] ...
4. [quote] ...
5. [exercise] the DO step
6. [closing] ...
"""
