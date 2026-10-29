#!/usr/bin/env python3
"""
deck_render.py — training.py's structured outline -> a rendered .pptx.

Bridges the LLM-produced outline (a curated, vocabulary-limited slide schema
— see training.SLIDE_KINDS) onto a theme backend: a module exporting a
`THEMES` tuple and `render(slides, pptx_path)`. `themes/studio.py` is the
default and ships everywhere; a private vendored engine can supply extra
themes when present, and is imported softly so its absence changes nothing
but the list of themes on offer. See themes/README.md for the contract.

All the mapping and curation lives here rather than in any backend, so a
backend stays a matter of paint and never has to re-derive this logic.
"""

from __future__ import annotations

import contextlib
import io
import logging
from pathlib import Path

from themes import studio

log = logging.getLogger(__name__)

# The private deck engine is OPTIONAL. `engine/` holds a vendored private renderer
# and its licensed fonts; a public checkout does not ship it, and Sori must
# still produce decks without it. So the import is soft, and `themes/studio.py`
# is the always-present default. See themes/README.md for the backend contract.
#
# deckgen also resolves its colour tokens at import and print()s a "tokens.css
# not found" WARNING to stdout when its design-token repo isn't a sibling checkout --
# which it never is here. The fallback it then uses is the canonical palette, so
# the message is noise on every launch. Swallow stdout for the import only; the
# vendored file itself is never edited.
try:
    with contextlib.redirect_stdout(io.StringIO()):
        from engine import deckgen, install_fonts
except Exception:  # pragma: no cover - absent by design
    log.debug("private deck engine not present; rendering with themes/studio")
    deckgen = None
    install_fonts = None

# User-facing theme name -> the mode string its backend wants. "baek" is
# the engine's white/hanji theme; in deckgen it IS "light" (light mode's
# background token is --bh-baek) -- there's no separate "baek" key in
# deckgen.MODES. THEMES stays a dict because the settings UI reads
# Object.keys(themes); engine entries come first so an installed engine keeps
# baek as the default.
_BH_MODES = {"baek": "light", "dark": "dark", "dancheong": "dancheong"}
THEMES = {**(_BH_MODES if deckgen is not None else {}), **{name: name for name in studio.THEMES}}
DEFAULT_THEME = "baek" if deckgen is not None else "studio"

# The mode a full_bleed section break flips to, so the deck's one polychrome
# moment carries real contrast against the body slides around it. dancheong is
# already high-chroma, so it stays as it is.
_CONTRAST_MODE = {"light": "dark", "dark": "light"}

# Body-slide kinds this bridge knows how to map. Must stay in sync with
# training.SLIDE_KINDS (cover/closing are synthesized below, not LLM-controlled).
_BODY_KINDS = {
    "divider",
    "content",
    "content_stat",
    "two_column",
    "process",
    "agenda",
    "quote",
    "callout",
    "full_bleed",
    "data",
    "scorecard",
    "chart",
}


class DeckRenderError(Exception):
    """A structurally invalid outline — caught by app.py as a TrainingError."""


def _pts(items) -> list[dict]:
    out = []
    for p in items or []:
        if not isinstance(p, dict):
            continue
        label = (p.get("label") or "").strip()
        if not label:
            continue
        out.append({"label": label, "sub": (p.get("sub") or "").strip()})
    return out


def _stats(items) -> list[dict]:
    """`data` supporting stats. A stat with no number is dropped rather than rendered
    as a bare label under a blank figure."""
    out = []
    for st in items or []:
        if not isinstance(st, dict):
            continue
        num = str(st.get("num") or "").strip()
        if not num:
            continue
        out.append(
            {"num": num, "label": (st.get("label") or "").strip(), "desc": (st.get("desc") or "").strip()}
        )
    return out


def _datums(items) -> list[dict]:
    """`chart` bars. Values must be real numbers -- deckgen calls float() on
    them and sorts, so a string here would blow up mid-render."""
    out = []
    for pt in items or []:
        if not isinstance(pt, dict):
            continue
        label = (pt.get("label") or "").strip()
        value = pt.get("value")
        if not label or not isinstance(value, (int, float)):
            continue
        out.append({"label": label, "value": float(value)})
    return out


def _rows(items) -> list[dict]:
    """`scorecard` rows. `level` is clamped to deckgen's 0-3 trigram range."""
    out = []
    for row in items or []:
        if not isinstance(row, dict):
            continue
        label = (row.get("label") or "").strip()
        if not label:
            continue
        level = row.get("level", 0)
        level = level if isinstance(level, int) else 0
        out.append({"label": label, "level": max(0, min(3, level)), "note": (row.get("note") or "").strip()})
    return out


def _slide_spec(raw: dict, mode: str) -> dict:
    kind = raw.get("kind")
    if kind not in _BODY_KINDS:
        raise DeckRenderError(f"Unknown or unsupported slide kind: {kind!r}")

    base = {"kind": kind, "mode": mode, "notes": raw.get("notes", "")}

    if kind == "divider":
        base.update(
            title=raw.get("heading", ""),
            eyebrow=raw.get("eyebrow", ""),
            lede=raw.get("lede", ""),
            meta=raw.get("meta", ""),
        )
    elif kind == "content":
        base.update(
            heading=raw.get("heading", ""),
            eyebrow=raw.get("eyebrow", ""),
            meta=raw.get("meta", ""),
            points=_pts(raw.get("points")),
            footer_l=raw.get("footer_l", ""),
            footer_r=raw.get("footer_r", ""),
        )
    elif kind == "content_stat":
        base.update(
            heading=raw.get("heading", ""),
            eyebrow=raw.get("eyebrow", ""),
            meta=raw.get("meta", ""),
            points=_pts(raw.get("points"))[:3],
            hero_stat=raw.get("hero_stat") or {},
            footer_l=raw.get("footer_l", ""),
        )
    elif kind == "two_column":
        left = raw.get("left") or {}
        right = raw.get("right") or {}
        # heading/lede/meta were previously dropped here, so a two_column slide
        # rendered as two unlabelled panes with no statement of what they were
        # comparing. Backends are free to ignore them; they must at least be
        # offered the same header every other body kind gets.
        base.update(
            eyebrow=raw.get("eyebrow", ""),
            heading=raw.get("heading", ""),
            lede=raw.get("lede", ""),
            meta=raw.get("meta", ""),
            left={"heading": left.get("heading", ""), "points": _pts(left.get("points"))},
            right={"heading": right.get("heading", ""), "points": _pts(right.get("points"))},
        )
    elif kind == "process":
        steps = _pts(raw.get("steps"))
        dominant = raw.get("dominant")
        if not isinstance(dominant, int) or not (0 <= dominant < max(len(steps), 1)):
            dominant = 0
        base.update(
            heading=raw.get("heading", ""), eyebrow=raw.get("eyebrow", ""), steps=steps, dominant=dominant
        )
    elif kind == "agenda":
        items = _pts(raw.get("items"))
        active = raw.get("active")
        active = active if isinstance(active, int) and 0 <= active < len(items) else None
        base.update(
            title=raw.get("heading", ""),
            eyebrow=raw.get("eyebrow", ""),
            meta=raw.get("meta", ""),
            items=items,
            active=active,
        )
    elif kind == "quote":
        base.update(
            quote=raw.get("quote", ""), attribution=raw.get("attribution", ""), eyebrow=raw.get("eyebrow", "")
        )
    elif kind == "callout":
        base.update(heading=raw.get("heading", ""), eyebrow=raw.get("eyebrow", ""), lede=raw.get("lede", ""))
    elif kind == "full_bleed":
        # full_bleed's whole job is to be the deck's one polychrome moment: a
        # colour field behind an angled mask. That field is painted in
        # m["border"], which in light mode is a pale hanji tint -- on a white
        # ground the "colour field" all but disappears and the section break
        # reads as a blank page. Flip this one slide to the contrasting mode so
        # the break actually lands. deckgen honours a per-slide "mode", and its
        # own DEFAULT_MODE table is dark for most body kinds, so a mixed-mode
        # deck is native to the engine rather than a hack.
        base["mode"] = _CONTRAST_MODE.get(mode, mode)
        # deckgen reads s["heading"] unguarded, so always supply one.
        base.update(
            heading=raw.get("heading", "") or " ",
            eyebrow=raw.get("eyebrow", ""),
            lede=raw.get("lede", ""),
            meta=raw.get("meta", ""),
        )
    elif kind == "data":
        base.update(
            eyebrow=raw.get("eyebrow", ""),
            rail_label=raw.get("rail_label", "") or "METRICS",
            hero_stat=raw.get("hero_stat") or {},
            stats=_stats(raw.get("stats"))[:2],
        )
    elif kind == "chart":
        base.update(
            heading=raw.get("heading", ""),
            eyebrow=raw.get("eyebrow", ""),
            meta=raw.get("meta", ""),
            chart_type=raw.get("chart_type", "") or "hbar",
            data=_datums(raw.get("data")),
            unit=raw.get("unit", ""),
            highlight=raw.get("highlight") if isinstance(raw.get("highlight"), int) else 0,
            footer_l=raw.get("footer_l", ""),
        )
    elif kind == "scorecard":
        base.update(
            heading=raw.get("heading", ""),
            eyebrow=raw.get("eyebrow", ""),
            meta=raw.get("meta", ""),
            rows=_rows(raw.get("rows")),
            footer_l=raw.get("footer_l", ""),
        )
    return base


def render_pptx(outline: dict, theme: str, out_path: Path) -> Path:
    """outline is training.generate_training()'s `.outline` dict: {title,
    subtitle, closing_heading, cta, slides}. Raises DeckRenderError on a
    structurally bad outline; deckgen itself is not defensive about that."""
    if theme not in THEMES:
        raise DeckRenderError(f"Unknown deck theme: {theme!r}. Available: {', '.join(THEMES)}.")
    use_bh = theme in _BH_MODES and deckgen is not None
    # The studio backend has no per-slide modes; pass its own name through so
    # _slide_spec's `mode` field stays a plain string either way.
    mode = _BH_MODES[theme] if use_bh else theme
    # Only the private engine needs fonts installed -- deckgen names Gowun
    # Batang and IBM Plex, which are not on a stock machine. `studio` names
    # only stock faces on purpose, so a public checkout installs nothing and
    # a deck it produces opens correctly on a machine that has never run Sori.
    if use_bh and install_fonts is not None:
        install_fonts.ensure_installed()  # best-effort; never blocks a render

    raw_slides = outline.get("slides") or []
    if not raw_slides:
        raise DeckRenderError("The training has no slides to render.")

    cover = {
        "kind": "cover",
        "mode": mode,
        "title": outline.get("title") or "Untitled training",
        "eyebrow": "SORI TRAINING",
        "lede": outline.get("subtitle", ""),
    }
    closing = {
        "kind": "closing",
        "mode": mode,
        "heading": outline.get("closing_heading") or "Keep building",
        "eyebrow": "SORI TRAINING",
        "cta": outline.get("cta", ""),
        "meta": outline.get("meta", ""),
    }
    slides = [cover] + [_slide_spec(s, mode) for s in raw_slides] + [closing]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    log.info("rendering %d slides with the %s theme", len(slides), theme)
    try:
        if use_bh:
            deckgen.build(slides, str(out_path))
        else:
            studio.render(slides, str(out_path))
    except KeyError as exc:
        backend = "deckgen" if use_bh else "themes.studio"
        raise DeckRenderError(f"{backend} doesn't recognize slide kind {exc}") from exc
    return out_path
