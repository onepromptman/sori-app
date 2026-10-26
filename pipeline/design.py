"""
design.py — one brief, several slide tools.

The L&D stage ends in `brief.md`. From there the deck can be made by any of
these backends; each gets a `handoff/<backend>/` folder beside the brief
with exactly what that tool needs, plus a README the deck-designer agent (or
a person) follows. The brief is never rewritten per backend; the hand-off
only adds the tool-specific wrapping.

| backend        | what renders                                   | needs                         | runs where |
|----------------|------------------------------------------------|-------------------------------|------------|
| offline        | python-pptx via train.py (studio or engine)    | nothing                       | here, now  |
| claude-design  | a Slides artifact with a design system attached| Claude session, design system | the agent  |
| dsign-html     | d_sign's HTML masters -> PDF/PNG/@dsCard       | a d_sign checkout + node      | the agent  |
| chatslide      | chatslide.ai from an uploaded PDF/DOCX         | a ChatSlide account           | the user   |
| figma          | Figma Slides via the figma-use-slides skill    | Figma connector               | the agent  |

Settings live in `<SORI_HOME>/pipeline.json` (not shows.json: the window's
bridge validates its own keys, and this is CLI-only for now):

    {"design_backend": "offline", "design_system_url": "https://claude.ai/artifact/...",
     "dsign_root": "~/repos/d_sign", "dsign_theme": "nok"}
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import brief as briefmod
from .ledger import state_dir

BACKENDS = ("offline", "claude-design", "dsign-html", "chatslide", "figma")
DEFAULT_BACKEND = "offline"
DEFAULTS = {"design_backend": DEFAULT_BACKEND, "design_system_url": "", "dsign_root": "",
            "dsign_theme": "nok"}


def config_path() -> Path:
    return state_dir() / "pipeline.json"


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(config_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(patch: dict) -> dict:
    cfg = load_config()
    for k, v in patch.items():
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
    if backend == "dsign-html":
        (out / "slide-map.json").write_text(json.dumps(_dsign_map(b, cfg), indent=2), encoding="utf-8")
    return out


def _evidence_md(b: briefmod.Brief) -> str:
    lines = [f"# Evidence — {b.title}", "", "Every quote below is verbatim from the transcript "
             "(checked by pipeline.brief.check). Use these words on slides; do not paraphrase a quote.", ""]
    for i, ev in enumerate(b.evidence, 1):
        stamp = f"[{ev['stamp']}] " if ev["stamp"] else ""
        why = f" — {ev['why']}" if ev["why"] else ""
        lines.append(f'{i}. {stamp}"{ev["quote"]}"{why}')
    return "\n".join(lines) + "\n"


def _slides_md(b: briefmod.Brief) -> str:
    return "\n".join(f"{s['n']}. [{s['kind']}] {s['text']}" for s in b.slides)


# d_sign masters by brief slide kind (themes/<mode>/<layout>.html). Kinds that
# have no master fall back to `content`.
DSIGN_MASTERS = {
    "cover": "title", "closing": "closing", "divider": "divider", "content": "content",
    "content_stat": "content-stat", "two_column": "twocol", "compare": "compare",
    "process": "process", "steps": "steps", "agenda": "agenda", "quote": "quote",
    "callout": "manifesto", "manifesto": "manifesto", "full_bleed": "full-bleed",
    "data": "data", "stat": "stat", "scorecard": "framework", "chart": "data",
    "timeline": "timeline", "code": "code", "exercise": "steps",
}


def _dsign_map(b: briefmod.Brief, cfg: dict) -> dict:
    theme = cfg.get("dsign_theme") or "nok"
    return {
        "theme": theme,
        "masters_dir": f"themes/{theme}/",
        "slides": [{"n": s["n"], "kind": s["kind"],
                    "master": f"themes/{theme}/{DSIGN_MASTERS.get(s['kind'], 'content')}.html",
                    "text": s["text"]} for s in b.slides],
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
    common = (f"# Hand-off: {b.title} → {backend}\n\n"
              f"Brief: `brief.md` (passed the sourcing gate). Quotes: `evidence.md`. "
              f"Slide order from the brief:\n\n{_slides_md(b)}\n\n"
              "Rules that travel with every backend: use the quotes word for word; a number on a slide "
              "must be in the transcript; the DO step gets its own slide; the study guide (if any) is the "
              "fuller version, the slides are terse.\n\n")
    if backend == "offline":
        return common + (
            "## Offline (python-pptx)\n\n"
            "1. Write `outline.json` next to the brief, following `python3 sori.py train --brief` "
            "(same rules, Sori's 12 slide kinds; map `exercise` to `process` or `scorecard`, "
            "`cover`/`closing` are synthesized).\n"
            "2. Render: `python3 sori.py train \"<transcript.txt>\" --outline outline.json --out \"" +
            str(ep_dir) + "\"`.\n"
            "3. Record: `python3 sori.py ledger add <episode_id> rendered deck-designer --artifact <deck.pptx>`.\n")
    if backend == "claude-design":
        ds = cfg.get("design_system_url") or "<not set: python3 sori.py design-system <url>>"
        return common + (
            "## Claude Design (Slides artifact)\n\n"
            f"Design system to attach: {ds}\n\n"
            "In a Claude session with the Artifact tool:\n"
            "1. `Artifact quickstart` with intent `slides`; pick the design system above (read its README first).\n"
            "2. Create the Slides artifact from the type it names, title = the brief title.\n"
            "3. Fill it from `brief.md` + `evidence.md`: one slide per numbered line, quotes verbatim, the DO step "
            "on its own slide. Keep the design system's rules (one mode, one accent, no cards).\n"
            "4. Export PPTX/PDF into this folder when done, and record: "
            "`python3 sori.py ledger add <episode_id> designed deck-designer --artifact <artifact url>`.\n"
            "Private by default: this is the owner's own deck; nothing is shared unless they share it.\n")
    if backend == "dsign-html":
        root = cfg.get("dsign_root") or "<not set: python3 sori.py design-config dsign_root <path>>"
        return common + (
            "## d_sign HTML masters (the canonical BH·SEOUL deck system)\n\n"
            f"Checkout: {root}   theme: {cfg.get('dsign_theme', 'nok')}\n\n"
            "`slide-map.json` maps each brief slide to a master under `themes/<theme>/`. Build as the "
            "exemplar deck does (`decks/m00-agentic-ai-fundamentals/BUILD-NOTES.md`): copy the master's CSS "
            "verbatim, swap content, keep `data-mode`, no new tokens; one file per slide plus a `player.html`. "
            "Gates: every slide `data-mode=\"<theme>\"`; every quote verbatim; no raw hex. Export with "
            "`node scripts/export-pdf.mjs` / `render.mjs`; the slides are already `@dsCard` files for Claude "
            "Design. Record `designed` in the ledger with the folder.\n")
    if backend == "chatslide":
        return common + (
            "## ChatSlide (chatslide.ai)\n\n"
            "ChatSlide builds a deck from an uploaded document; there is no public API, so this step is a "
            "person's: upload `source-document.md` (or export it to PDF/DOCX first) at chatslide.ai, pick a "
            "template, generate, then download the PPTX into this folder. The document already carries the "
            "slide order and the verbatim quotes so the tool structures rather than invents. Record `designed` "
            "with the PPTX path.\n")
    if backend == "figma":
        return common + (
            "## Figma Slides\n\n"
            "In a session with the Figma connector and the `figma-use-slides` skill: create a Slides file, "
            "set the theme from your design system (the d_sign tokens if available), then one slide per "
            "numbered line, quotes verbatim. Record `designed` with the Figma file URL.\n")
    return common
