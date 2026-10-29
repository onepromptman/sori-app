#!/usr/bin/env python3
"""
training.py — transcript -> training content (deck outline + study guide),
via the Claude API, or from an outline a Claude Code session wrote itself.

Whisper (transcribe.py) only converts speech to text. Writing a training
deck is a different job — synthesizing, curating, and phrasing content — and
that needs a language model, which the app has nowhere else to do it. In the
exe that model is reached through the Claude API (the one step that costs
money and needs a key). In the Claude-native door the session IS the model:
it writes the outline against the same rules and schema (`train.py --brief`)
and hands it to result_from_outline() via `train.py --outline`, so no key is
needed and no logic lives in the skill. See README.md for the trade-off.

Pure engine module, no UI, no filesystem writes — mirrors transcribe.py's
role. One call in (transcript text + episode metadata), one TrainingResult
out; app.py's run_training() does the file writing (same split as
transcribe.py / run_transcription()).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-5"

# Slide kinds the LLM is allowed to produce.
#
# The original vocabulary excluded image/chart/data/scorecard/full_bleed
# wholesale, on the grounds that they "need a real image or a precise numeric
# series". That guard is right about the risk -- inventing numbers to fill a
# stat slide is exactly the unsourced claim OnePromptMan's other training-deck work
# gates against -- but it over-applied to two of the five, so the rule is now
# enforced per kind instead of by blanket exclusion:
#
#   full_bleed  ADMITTED. Needs neither an image nor a number: it is a colour
#               field + angled mask + type. Zero fabrication surface. Counts
#               against deckgen's <=3 "polychrome moment" budget, though, and
#               cover+closing already spend two -- so at most ONE per deck
#               (enforced in _validate_slide_data below).
#   data        ADMITTED. Carries a hero_stat plus <=2 supporting stats: the same
#               literal-number constraint content_stat already lives under,
#               applied three times instead of once. Every num must appear in
#               the transcript verbatim.
#   scorecard   ADMITTED as a facilitator instrument only. The 0-3 levels are
#               the room's judgement about its own stack, never a claim about
#               anything in the episode, so rows ship at level 0 and the note
#               column carries the transcript fact that motivates the row.
#   chart       ADMITTED but hard-gated: >=3 data points that are all literally
#               stated in the transcript AND share one unit. Most episodes have
#               no such series; the honest answer then is not to use it.
#   image       STILL EXCLUDED. Sori has no image pipeline to source from.
#
# cover/closing stay out because deck_render.py synthesizes those from
# deck_title/subtitle/cta so every deck gets a consistent, on-brand bookend.
SLIDE_KINDS = [
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
]

# Kinds admitted above that carry a fabrication risk, and so get extra
# structural validation in _validate_slide_data().
_NUMERIC_KINDS = {"data", "chart"}

_POINT_SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string"}, "sub": {"type": "string"}},
    "required": ["label"],
}
_PANE_SCHEMA = {
    "type": "object",
    "properties": {"heading": {"type": "string"}, "points": {"type": "array", "items": _POINT_SCHEMA}},
}
# One supporting figure on a `data` slide -- same shape as hero_stat.
_STAT_SCHEMA = {
    "type": "object",
    "properties": {"num": {"type": "string"}, "label": {"type": "string"}, "desc": {"type": "string"}},
    "required": ["num"],
}
# One bar on a `chart` slide. `value` is numeric so the renderer can scale it;
# the unit lives once on the slide, not per point.
_DATUM_SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string"}, "value": {"type": "number"}},
    "required": ["label", "value"],
}
# One row on a `scorecard`. `level` is the audience's own 0-3 rating.
_ROW_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "level": {"type": "integer", "minimum": 0, "maximum": 3},
        "note": {"type": "string"},
    },
    "required": ["label"],
}

TOOL_SCHEMA = {
    "name": "submit_training",
    "description": "Submit the finished training deck outline and study guide.",
    "input_schema": {
        "type": "object",
        "required": ["deck_title", "slides", "study_guide_markdown"],
        "properties": {
            "deck_title": {
                "type": "string",
                "description": "Deck cover title. \\n allowed for a line break.",
            },
            "deck_subtitle": {"type": "string"},
            "closing_heading": {"type": "string", "description": "Final slide's headline."},
            "cta": {"type": "string", "description": "One short closing call-to-action line."},
            "slides": {
                "type": "array",
                "minItems": 6,
                "maxItems": 20,
                "items": {
                    "type": "object",
                    "required": ["kind"],
                    "properties": {
                        "kind": {"type": "string", "enum": SLIDE_KINDS},
                        "eyebrow": {"type": "string", "description": "Short all-caps kicker label."},
                        "heading": {"type": "string"},
                        "lede": {"type": "string"},
                        "meta": {"type": "string"},
                        "points": {
                            "type": "array",
                            "items": _POINT_SCHEMA,
                            "description": "Bullets for content/content_stat kinds.",
                        },
                        "hero_stat": {
                            "type": "object",
                            "properties": {
                                "num": {"type": "string"},
                                "label": {"type": "string"},
                                "desc": {"type": "string"},
                            },
                            "description": "content_stat only -- must be a number literally stated in the transcript.",
                        },
                        "steps": {
                            "type": "array",
                            "items": _POINT_SCHEMA,
                            "description": "process kind: ordered steps/stages.",
                        },
                        "dominant": {
                            "type": "integer",
                            "description": "process kind: 0-based index of the step to emphasize.",
                        },
                        "items": {
                            "type": "array",
                            "items": _POINT_SCHEMA,
                            "description": "agenda kind: numbered list.",
                        },
                        "active": {
                            "type": "integer",
                            "description": "agenda kind: 0-based index of the highlighted item.",
                        },
                        "left": _PANE_SCHEMA,
                        "right": _PANE_SCHEMA,
                        "quote": {
                            "type": "string",
                            "description": "quote kind: verbatim from the transcript.",
                        },
                        "attribution": {"type": "string"},
                        "stats": {
                            "type": "array",
                            "maxItems": 2,
                            "items": _STAT_SCHEMA,
                            "description": (
                                "data kind: up to 2 supporting figures beside the "
                                "hero_stat. Every num must be literally stated in "
                                "the transcript."
                            ),
                        },
                        "rail_label": {
                            "type": "string",
                            "description": (
                                "data kind: short word printed vertically up the "
                                "left rail, e.g. METRICS or OUTAGE."
                            ),
                        },
                        "chart_type": {
                            "type": "string",
                            "enum": ["hbar"],
                            "description": "chart kind: only 'hbar' is implemented.",
                        },
                        "data": {
                            "type": "array",
                            "minItems": 3,
                            "items": _DATUM_SCHEMA,
                            "description": (
                                "chart kind: >=3 points, each value literally stated "
                                "in the transcript and all sharing one unit. Bars are "
                                "sorted descending automatically."
                            ),
                        },
                        "unit": {
                            "type": "string",
                            "description": "chart kind: unit suffix appended to every value, e.g. '%'.",
                        },
                        "highlight": {
                            "type": "integer",
                            "description": "chart kind: 0-based index (into `data` as written) of the bar to accent.",
                        },
                        "rows": {
                            "type": "array",
                            "items": _ROW_SCHEMA,
                            "description": (
                                "scorecard kind: self-assessment rows. `level` is the "
                                "room's own 0-3 rating and ships at 0; `note` carries "
                                "the transcript fact that motivates the row."
                            ),
                        },
                        "footer_l": {"type": "string"},
                        "footer_r": {"type": "string"},
                        "notes": {"type": "string", "description": "Speaker notes for this slide."},
                    },
                },
            },
            "study_guide_markdown": {
                "type": "string",
                "description": (
                    "A standalone markdown study guide: summary, key takeaways, "
                    "and 3-6 discussion/quiz questions. Grounded only in the "
                    "transcript -- no content that isn't also in the deck or the "
                    "transcript itself."
                ),
            },
        },
    },
}

SYSTEM_PROMPT = (
    "You turn a podcast/YouTube transcript into a training deck outline and a "
    "study guide for an internal AI-training curriculum. Hard rules:\n"
    "1. Every claim, quote, and number must come from the transcript. Never "
    "invent statistics, dates, or attributions you can't point to in the text.\n"
    "2. If the transcript doesn't clearly support a hero_stat, don't force one "
    "-- use a content/callout/quote slide instead of fabricating a number.\n"
    "3. Prefer concrete, worked examples from the transcript over generic "
    "restatement of the topic.\n"
    "4. Keep slide text terse -- these are presentation slides, not paragraphs; "
    "3-5 short bullets max per slide.\n"
    "5. The study guide is the fuller version: a short summary, key takeaways, "
    "and 3-6 discussion/quiz questions a facilitator could actually run a "
    "session with.\n"
    "6. The visual kinds carry the same sourcing rule, and each has a gate:\n"
    "   - `data`: hero_stat plus up to 2 supporting stats. Every `num` must appear "
    "in the transcript verbatim. Three real figures or use `content_stat`.\n"
    "   - `chart`: needs >=3 values that are ALL literally stated AND share "
    "one unit (all percentages, all dollars, all counts of the same thing). "
    "Do not mix a benchmark score with a discount, and never derive a value "
    "by arithmetic the speaker did not state. Most episodes have no such "
    "series -- when yours does not, simply do not use this kind.\n"
    "   - `scorecard`: a facilitator instrument, never a claim. Ship every "
    "row at level 0 for the room to rate itself; put the transcript fact that "
    "motivates the row in `note`.\n"
    "   - `full_bleed`: a section statement, no data. At most ONE per deck.\n"
    "7. Vary the archetypes. Three identical body kinds in a row reads as a "
    "wall; break the run with a divider, quote, or callout."
)

# Claude has a real context window, but a training deck doesn't need a
# three-hour episode verbatim; truncate defensively so one runaway episode
# can't blow the request (or the bill) up unexpectedly.
MAX_TRANSCRIPT_CHARS = 60_000


class TrainingGenerationError(Exception):
    """A Claude call that failed, or returned something unusable."""


def _validate_slide_data(i: int, sl: dict) -> None:
    """Structural gates for the kinds that can carry fabricated numbers.

    These cannot check that a figure is *in* the transcript -- nothing here
    has the transcript -- but they refuse the shapes that make fabrication
    easy: a stat slide with no stat, a one-bar "chart", a chart whose values
    were clearly assembled from unlike things. The sourcing rule itself is
    carried by SYSTEM_PROMPT rule 6 and enforced by the author.
    """
    kind = sl.get("kind")

    if kind == "data":
        hero = sl.get("hero_stat") or {}
        if not str(hero.get("num", "")).strip():
            raise TrainingGenerationError(
                f"Slide {i} is a data slide with no hero_stat.num. Use content or "
                "callout when the transcript has no figure to anchor on."
            )
        for j, st in enumerate(sl.get("stats") or [], 1):
            if not str((st or {}).get("num", "")).strip():
                raise TrainingGenerationError(f"Slide {i} supporting stat {j} has no num.")

    elif kind == "chart":
        pts = sl.get("data") or []
        if len(pts) < 3:
            raise TrainingGenerationError(
                f"Slide {i} is a chart with {len(pts)} point(s); a chart needs at "
                "least 3 values that are all literally stated in the transcript "
                "and share one unit. With fewer, use data or content_stat."
            )
        for j, pt in enumerate(pts, 1):
            if not isinstance((pt or {}).get("value"), (int, float)):
                raise TrainingGenerationError(f"Slide {i} chart point {j} has a non-numeric value.")
            if not str((pt or {}).get("label", "")).strip():
                raise TrainingGenerationError(f"Slide {i} chart point {j} has no label.")

    elif kind == "scorecard":
        rows = sl.get("rows") or []
        if not rows:
            raise TrainingGenerationError(f"Slide {i} is a scorecard with no rows.")
        for j, row in enumerate(rows, 1):
            if not str((row or {}).get("label", "")).strip():
                raise TrainingGenerationError(f"Slide {i} scorecard row {j} has no label.")
            lvl = (row or {}).get("level", 0)
            if not isinstance(lvl, int) or not 0 <= lvl <= 3:
                raise TrainingGenerationError(f"Slide {i} scorecard row {j} has level {lvl!r}; must be 0-3.")


@dataclass
class TrainingResult:
    outline: dict  # {"title", "subtitle", "closing_heading", "cta", "slides"}
    study_guide_md: str


def generate_training(
    transcript_text: str, meta: dict, api_key: str, model: str = DEFAULT_MODEL
) -> TrainingResult:
    """One Claude call: transcript in, a deck outline + study guide out.

    Raises TrainingGenerationError on anything that keeps this from being a
    usable result — a missing dependency, a rejected key, an empty
    transcript, or a response that doesn't actually contain a training.
    """
    try:
        import anthropic
    except ImportError as exc:
        raise TrainingGenerationError(
            "The anthropic package isn't installed, so training generation isn't available."
        ) from exc

    text = (transcript_text or "").strip()
    if not text:
        raise TrainingGenerationError("This transcript is empty — nothing to train on.")

    truncated = len(text) > MAX_TRANSCRIPT_CHARS
    if truncated:
        text = text[:MAX_TRANSCRIPT_CHARS]

    user_prompt = (
        f"Episode: {meta.get('title', '')}\n"
        f"Show: {meta.get('show', '')}\n"
        f"Date: {meta.get('date', '')}\n\n"
        f"Transcript{' (truncated)' if truncated else ''}:\n{text}"
    )

    client = anthropic.Anthropic(api_key=api_key)
    log.info(
        "calling %s for a training (%d transcript chars%s)",
        model,
        len(text),
        ", truncated" if truncated else "",
    )
    try:
        response = client.messages.create(
            model=model,
            # 20 slides x (bullets + speaker notes) plus a full study guide can
            # run well past a small budget -- a truncated tool call otherwise
            # surfaces as a confusing "no slides"/"no study guide" error on a
            # run that already cost money.
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "submit_training"},
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.AuthenticationError as exc:
        raise TrainingGenerationError("That Claude API key was rejected — check it in Settings.") from exc
    except anthropic.APIError as exc:
        raise TrainingGenerationError(f"Claude API error: {exc}") from exc
    except Exception as exc:
        raise TrainingGenerationError(f"Couldn't reach the Claude API: {exc}") from exc

    if response.stop_reason == "max_tokens":
        raise TrainingGenerationError(
            "This training ran too long to finish (Claude hit its output limit "
            "mid-response) — the transcript may be too dense for one pass. Try again."
        )

    call = next((b for b in response.content if getattr(b, "type", None) == "tool_use"), None)
    if call is None:
        raise TrainingGenerationError("Claude didn't return a training — try again.")
    return result_from_outline(call.input or {}, meta)


def result_from_outline(data: dict, meta: dict) -> TrainingResult:
    """Turn a `submit_training` payload into a TrainingResult, or raise.

    Shared by both doors: the API path hands over the tool_use input, the
    Claude-native path hands over an outline JSON the session wrote itself
    (train.py --outline). Same checks either way, so a deck is a deck no
    matter who authored the outline. Structural validation mirrors the
    parts of TOOL_SCHEMA the API would have enforced.
    """
    if not isinstance(data, dict):
        raise TrainingGenerationError("The outline must be a JSON object.")
    slides = data.get("slides") or []
    if not slides:
        raise TrainingGenerationError("Claude returned a training with no slides.")
    if not isinstance(slides, list) or not all(isinstance(sl, dict) for sl in slides):
        raise TrainingGenerationError("`slides` must be a list of objects.")
    lo = TOOL_SCHEMA["input_schema"]["properties"]["slides"]["minItems"]
    hi = TOOL_SCHEMA["input_schema"]["properties"]["slides"]["maxItems"]
    if not lo <= len(slides) <= hi:
        raise TrainingGenerationError(
            f"A training needs {lo} to {hi} slides; this outline has {len(slides)}."
        )
    for i, sl in enumerate(slides, 1):
        kind = sl.get("kind")
        if kind not in SLIDE_KINDS:
            raise TrainingGenerationError(f"Slide {i} has kind {kind!r}; allowed: {', '.join(SLIDE_KINDS)}.")
        if kind == "quote" and not (sl.get("quote") or "").strip():
            raise TrainingGenerationError(f"Slide {i} is a quote slide with no quote.")
        _validate_slide_data(i, sl)

    full_bleeds = sum(1 for sl in slides if sl.get("kind") == "full_bleed")
    if full_bleeds > 1:
        raise TrainingGenerationError(
            f"{full_bleeds} full_bleed slides; at most 1 per deck (deckgen budgets "
            "3 polychrome moments and cover/closing already use two)."
        )

    guide = (data.get("study_guide_markdown") or "").strip()
    if not guide:
        raise TrainingGenerationError("Claude returned a training with no study guide.")

    outline = {
        "title": data.get("deck_title") or meta.get("title") or "Untitled training",
        "subtitle": data.get("deck_subtitle", ""),
        "closing_heading": data.get("closing_heading", ""),
        "cta": data.get("cta", ""),
        "slides": slides,
    }
    return TrainingResult(outline=outline, study_guide_md=guide)


def outline_brief() -> str:
    """The authoring brief for a session writing the outline itself: the same
    house rules the API path sends as the system prompt, plus the exact JSON
    shape `train.py --outline` accepts. Printed by `train.py --brief`."""
    import json

    return (
        SYSTEM_PROMPT + "\n\nWrite ONE JSON object matching this schema (the `input_schema` of the "
        "submit_training tool) and save it as outline.json:\n"
        + json.dumps(TOOL_SCHEMA["input_schema"], indent=2)
    )
