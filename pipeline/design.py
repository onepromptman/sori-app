"""
design.py \u2014 one brief, several slide tools.

The L&D stage ends in `brief.md`. From there the deck can be made by any of
these backends; each gets a `handoff/<backend>/` folder beside the brief
with exactly what that tool needs, plus a README the deck-designer agent (or
a person) follows. The brief is never rewritten per backend; the hand-off
only adds the tool-specific wrapping.

| backend        | what renders                                   | needs                         | runs where |
|----------------|------------------------------------------------|-------------------------------|------------|
| offline        | python-pptx via train.py (studio or engine)    | nothing                       | here, now  |
| claude-design  | a Slides artifact with a design system attached| Claude session, design system | the agent  |
| html     | HTML layout plan for your own renderer       | your own HTML templates      | the agent  |
| chatslide      | chatslide.ai from an uploaded PDF/DOCX         | a ChatSlide account           | the user   |
| figma          | Figma Slides via the figma-use-slides skill    | Figma connector               | the agent  |

Settings live in `<SORI_HOME>/pipeline.json` (not shows.json: the window's
bridge validates its own keys, and this is CLI-only for now):

    {"design_backend": "offline", "design_system_url": "https://claude.ai/artifact/...",
     "html_root": "<your-template-folder>", "html_theme": "default"}
"""

from __future__ import annotations

import json
import shlex
import shutil
from pathlib import Path

from . import brief as briefmod
from .ledger import state_dir

BACKENDS = ("offline", "claude-design", "html", "chatslide", "figma")
DEFAULT_BACKEND = "offline"
DEFAULTS = {
    "design_backend": DEFAULT_BACKEND,
    "design_system_url": "",
    "html_root": "",
    "html_theme": "default",
}


def config_path() -> Path:
    return state_dir() / "pipeline.json"


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        stored = json.loads(config_path().read_text(encoding="utf-8"))
        if isinstance(stored, dict):
            cfg.update(
                {key: value for key, value in stored.items() if key in DEFAULTS and isinstance(value, str)}
            )
    except (OSError, ValueError):
        pass
    return cfg


def save_config(patch: dict) -> dict:
    cfg = load_config()
    for k, v in patch.items():
        if not isinstance(v, str):
            raise ValueError("pipeline setting values must be text")
        if k not in DEFAULTS:
            raise ValueError(f"unknown pipeline setting {k!r}; one of {', '.join(DEFAULTS)}")
        if k == "design_backend" and v not in BACKENDS:
            raise ValueError(f"unknown backend {v!r}; one of {', '.join(BACKENDS)}")
        cfg[k] = v
    tmp = config_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    tmp.replace(config_path())
    return cfg


class HandoffError(Exception):
    pass


def find_transcript(ep_dir: Path) -> Path | None:
    """The transcript for an episode folder: a copy inside it, else the sweep's
    file under Transcripts/<Show>/<same name>.txt."""
    local = sorted(ep_dir.glob("*.txt"))
    if local:
        return local[0]
    candidate = state_dir() / "Transcripts" / ep_dir.parent.name / (ep_dir.name + ".txt")
    return candidate if candidate.exists() else None


def handoff(ep_dir: Path, backend: str, cfg: dict | None = None) -> Path:
    """Write `handoff/<backend>/` for an episode whose brief passes the gate.
    Returns the folder. Raises HandoffError on a missing or failing brief."""
    if backend not in BACKENDS:
        raise HandoffError(f"unknown backend {backend!r}; one of {', '.join(BACKENDS)}")
    cfg = cfg or load_config()
    brief_path = ep_dir / "brief.md"
    if not brief_path.exists():
        raise HandoffError(f"no brief.md in {ep_dir}; run the L&D stage first (/sori:curate)")
    transcript = find_transcript(ep_dir)
    if transcript is None:
        raise HandoffError(f"no transcript found for {ep_dir.name}")
    report = briefmod.check_files(brief_path, transcript)
    if not report.ok:
        raise HandoffError("brief fails the sourcing gate:\n" + str(report))

    out = ep_dir / "handoff" / backend
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(brief_path, out / "brief.md")
    b = briefmod.parse(brief_path.read_text(encoding="utf-8"))
    (out / "evidence.md").write_text(_evidence_md(b), encoding="utf-8")
    for extra in ("outline.json", "critique.md", "triage.json"):
        if (ep_dir / extra).exists():
            shutil.copy2(ep_dir / extra, out / extra)
    (out / "README.md").write_text(_readme(backend, b, cfg, ep_dir), encoding="utf-8")
    if backend == "chatslide":
        (out / "source-document.md").write_text(_chatslide_doc(b), encoding="utf-8")
    if backend == "html":
        (out / "slide-map.json").write_text(json.dumps(_html_map(b, cfg), indent=2), encoding="utf-8")
    return out


def _evidence_md(b: briefmod.Brief) -> str:
    lines = [
        f"# Evidence \u2014 {b.title}",
        "",
        "Every quote below is verbatim from the transcript "
        "(checked by pipeline.brief.check). Use these words on slides; do not paraphrase a quote.",
        "",
    ]
    for i, ev in enumerate(b.evidence, 1):
        stamp = f"[{ev['stamp']}] " if ev["stamp"] else ""
        why = f" \u2014 {ev['why']}" if ev["why"] else ""
        lines.append(f'{i}. {stamp}"{ev["quote"]}"{why}')
    return "\n".join(lines) + "\n"


def _slides_md(b: briefmod.Brief) -> str:
    return "\n".join(f"{s['n']}. [{s['kind']}] {s['text']}" for s in b.slides)


# Generic HTML layouts by brief slide kind (themes/<mode>/<layout>.html). Kinds that
# have no master fall back to `content`.
HTML_LAYOUTS = {
    "cover": "title",
    "closing": "closing",
    "divider": "divider",
    "content": "content",
    "content_stat": "content-stat",
    "two_column": "twocol",
    "compare": "compare",
    "process": "process",
    "steps": "steps",
    "agenda": "agenda",
    "quote": "quote",
    "callout": "manifesto",
    "manifesto": "manifesto",
    "full_bleed": "full-bleed",
    "data": "data",
    "stat": "stat",
    "scorecard": "framework",
    "chart": "data",
    "timeline": "timeline",
    "code": "code",
    "exercise": "steps",
}


def _html_map(b: briefmod.Brief, cfg: dict) -> dict:
    theme = cfg.get("html_theme") or "default"
    return {
        "theme": theme,
        "masters_dir": f"themes/{theme}/",
        "slides": [
            {
                "n": s["n"],
                "kind": s["kind"],
                "master": f"themes/{theme}/{HTML_LAYOUTS.get(s['kind'], 'content')}.html",
                "text": s["text"],
            }
            for s in b.slides
        ],
    }


def _chatslide_doc(b: briefmod.Brief) -> str:
    """ChatSlide builds from an uploaded document. Give it one that already
    has the slide order and the exact quotes, so it structures rather than
    invents."""
    parts = [f"# {b.title}", "", b.sections.get("Audience", ""), "", "## Learning objectives", ""]
    parts += [f"- {o}" for o in b.objectives]
    parts += ["", "## Slides, in order", ""]
    for s in b.slides:
        parts.append(f"### Slide {s['n']}: {s['text']}")
        parts.append(f"Layout: {s['kind'].replace('_', ' ')}.")
        parts.append("")
    parts += ["## Quotes to use verbatim", ""]
    parts += [f'- "{ev["quote"]}"' + (f" ({ev['stamp']})" if ev["stamp"] else "") for ev in b.evidence]
    parts += ["", "## Exercise", "", b.sections.get("DO step", "")]
    return "\n".join(parts) + "\n"


def _readme(backend: str, b: briefmod.Brief, cfg: dict, ep_dir: Path) -> str:
    common = (
        f"# Hand-off: {b.title} → {backend}\n\n"
        f"Brief: `brief.md` (passed the sourcing gate). Quotes: `evidence.md`. "
        f"Slide order from the brief:\n\n{_slides_md(b)}\n\n"
        "Rules that travel with every backend: use the quotes word for word; a number on a slide "
        "must be in the transcript; the DO step gets its own slide; the study guide (if any) is the "
        "fuller version, the slides are terse.\n\n"
    )
    if backend == "offline":
        return common + (
            "## Offline (python-pptx)\n\n"
            "1. Write `outline.json` next to the brief, following `python3 sori.py train --brief` "
            "(same rules, Sori's 12 slide kinds; map `exercise` to `process` or `scorecard`, "
            "`cover`/`closing` are synthesized).\n"
            "2. Render: `python3 sori.py design " + shlex.quote(str(ep_dir)) + "` (it calls train.py "
            "in-process with the transcript and outline.json; no path goes through a shell).\n"
            "3. Record: `python3 sori.py ledger add <episode_id> rendered deck-designer --artifact <deck.pptx>`.\n"
        )
    if backend == "claude-design":
        return common + (
            "## Claude slide handoff\n\n"
            "Use brief.md and evidence.md in a Claude client with slide authoring support. "
            "Check the client's available tools and data-sharing settings before uploading. "
            "This is a manual handoff, not an automated integration.\n"
            "Optional design system: " + str(cfg.get("design_system_url") or "none") + "\n"
        )
    if backend == "html":
        return common + (
            "## HTML slide handoff\n\n"
            "Use slide-map.json as a layout plan for your own HTML renderer. "
            "This handoff does not include templates or execute a renderer. "
            "Read the renderer's documentation and review its output against the source.\n"
        )
    if backend == "chatslide":
        return common + (
            "## ChatSlide (chatslide.ai)\n\n"
            "ChatSlide builds a deck from an uploaded document; this package provides a manual handoff, so this step is a "
            "person's: upload `source-document.md` (or export it to PDF/DOCX first) at chatslide.ai, pick a "
            "template, generate, then download the PPTX into this folder. The document already carries the "
            "slide order and the verbatim quotes so the tool structures rather than invents. Record `designed` "
            "with the PPTX path.\n"
        )
    if backend == "figma":
        return common + (
            "## Figma Slides\n\n"
            "In a session with a supported Figma Slides authoring tool: create a Slides file, "
            "set the theme from your design system, then one slide per "
            "numbered line, quotes verbatim. Record `designed` with the Figma file URL.\n"
        )
    return common
