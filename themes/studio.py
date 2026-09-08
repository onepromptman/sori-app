#!/usr/bin/env python3
"""themes/studio.py — Sori's default deck theme.

An unbranded editorial theme covering every slide kind in
`training.SLIDE_KINDS` plus the synthesized cover and closing. It ships as the
default so Sori produces a presentable deck out of the box, with no private
design assets and no font installation.

Where the numbers come from
---------------------------
The proportions, palette roles and composition rules are lifted from a working
design system rather than invented: warm paper ground instead of pure white,
ink with a blue undertone instead of black, ONE load-bearing accent, and a
second "pop" colour spent on roughly one element per deck. The type scale is
the important part — two anchors (a display size and a body size) with nothing
in between. Mid-sized subheads are what make generated decks read as
generated, so there is no mid size here to reach for.

Sizes are given in points; the source system is expressed in CSS pixels on a
1280x720 canvas, which maps to PowerPoint's 13.333x7.5in widescreen slide at
exactly 0.75pt per px, so every value below is a source value x 0.75.

It is meant to be replaced. See themes/README.md; the contract is one
function::

    render(slides: list[dict], pptx_path: str) -> None

where `slides` is the list of dicts `deck_render._slide_spec()` produces.
"""
from __future__ import annotations

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

SW_IN, SH_IN = 13.333, 7.5      # 16:9, matching PowerPoint's widescreen default
PAD_X, PAD_Y = 0.917, 0.75      # 88px / 72px of source padding
COL_W = SW_IN - 2 * PAD_X       # 11.5in of usable width

# --- palette ---------------------------------------------------------------
# Light surfaces. PAPER is deliberately not #FFFFFF and INK is deliberately not
# #000000: a warm ground and a cool ink read as chosen, where pure black on
# pure white reads as unstyled. MUTED/LINE are pre-blended against PAPER
# because python-pptx has no alpha on text.
PAPER = "F7F7F4"
PANEL = "ECECE6"
INK = "14171C"
MUTED = "6F7172"
LINE = "D7D8D6"
METAL = "C9A24B"        # hairline gold — structure, never text
ACCENT = "0B4DA2"       # cobalt: THE load-bearing colour
POP = "C8202E"          # spent once or twice per deck, never as body colour

# Dark surfaces carry the cover, the section breaks and the closing. Gold takes
# over as the load-bearing accent there: cobalt on near-black has too little
# separation to do any work.
DARK = "14171C"
DARK_INK = "F7F7F4"
DARK_MUTED = "A1A2A2"
DARK_LINE = "3D3F43"
DARK_ACCENT = "C9A24B"

# --- type ------------------------------------------------------------------
# Stock faces only. Nothing to install, nothing to bundle, nothing to go wrong
# on someone else's machine.
#
# This is a deliberate constraint rather than a compromise. OOXML stores one
# font *name* per run: there is no fallback chain, and python-pptx cannot
# embed a face. So naming a font the opening machine lacks does not degrade to
# your second choice -- PowerPoint substitutes its own default and the deck
# arrives looking broken. A deck that is going to be forwarded, opened on a
# colleague's laptop and edited can only safely name fonts that are already
# everywhere.
#
# Georgia is the load-bearing one: it carries every headline, and it ships on
# Windows and macOS both. Segoe UI and Consolas are Windows faces used at body
# and label sizes, where a substitution costs little.
FONT_DISPLAY = "Georgia"
FONT_BODY = "Segoe UI"
FONT_MONO = "Consolas"
FONT_NUMERAL = "Consolas"


def _num(emphasis: bool = True):
    """(family, bold) for a figure. Consolas has a real bold, so weight comes
    from the flag."""
    return FONT_MONO, emphasis


# Two anchors and their satellites. Nothing lives between T_H1 and T_BODY:
# reaching for a mid-sized subhead is the clearest tell that a deck was
# generated rather than set, so there is no mid size here to reach for.
T_STAT = 99.0           # the numeral IS the slide
T_DISPLAY = 69.0
T_COVER = 63.0
T_H1 = 45.0
T_UNIT = 36.0
T_SAT = 24.0
T_BODY = 15.0
T_SMALL = 11.25
T_EYEBROW = 9.75
T_MICRO = 8.25

# Letter-spacing, in em, for the uppercase mono labels. Written to the run's
# XML `spc` attribute, never faked by interleaving spaces into the string.
TRACK_EYEBROW = 0.20
TRACK_LABEL = 0.16
TRACK_MICRO = 0.14


# --- vertical slots --------------------------------------------------------
# Fixed so every body slide shares a baseline and headings can wrap two lines
# without colliding with what follows.
Y_CHROME = 0.55
Y_EYEBROW = 1.12
Y_HEAD = 1.44
Y_RULE = 2.86
Y_FOOT = 6.62


def _rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h)


def _txt(slide, x, y, w, h, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    return tf


def _run(p, text, font, size, colour, bold=False, upper=False, align=None,
         space_after=0.0, track=0.0):
    """`track` is letter-spacing in em. It is written straight to the run's
    XML `spc` attribute (hundredths of a point) because python-pptx exposes no
    API for it. The tempting shortcut -- interleaving spaces into the string --
    would put "A  M O N T H" in the file, so anyone editing or copying from
    the deck inherits garbage. The deck has to be editable, not just look
    right in a PDF."""
    if align is not None:
        p.alignment = align
    p.space_after = Pt(space_after)
    r = p.add_run()
    r.text = (text or "").upper() if upper else (text or "")
    r.font.name = font
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = _rgb(colour)
    if track:
        r._r.get_or_add_rPr().set("spc", str(int(round(size * track * 100))))
    return r


def _para(tf, first: bool):
    return tf.paragraphs[0] if first else tf.add_paragraph()


def _rect(slide, x, y, w, h, colour):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                                Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = _rgb(colour)
    sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def _dot(slide, x, y, d, colour):
    sh = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y),
                                Inches(d), Inches(d))
    sh.fill.solid()
    sh.fill.fore_color.rgb = _rgb(colour)
    sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def _bg(slide, colour):
    _rect(slide, 0, 0, SW_IN, SH_IN, colour)


# Average character advance as a fraction of the point size, per face. These
# are the difference between a layout that holds and one that overprints:
# python-pptx cannot measure text, so every stacked layout below budgets its
# rows from an estimate, and an estimate that runs optimistic silently puts
# the next block on top of this one.
#
# Measured, not guessed, over a sample of real headings (reproduce with
# PIL.ImageFont.truetype(face, 200).getlength(s) / 200 / len(s)):
#
#     Georgia Bold  0.529 avg / 0.562 max     Segoe UI  0.457 avg / 0.481 max
#
# The constants take the observed max plus headroom, because the cost of
# over-estimating is a little extra whitespace and the cost of
# under-estimating is overprinted text. Change a font and re-measure.
ADV_BODY = 0.51
ADV_DISPLAY = 0.59


def _wrapped_lines(text: str, width_in: float, pt: float,
                   adv: float | None = None) -> int:
    """How many lines `text` needs at `pt` in a box `width_in` wide. `adv`
    defaults to the *current* body advance rather than binding it as a default
    argument, which would freeze whichever font set was active at import.

    Hard line breaks are counted separately from wrapping. An outline is free
    to write "Concentration\nrisk" to control where a headline turns, and
    measuring that as one 17-character line puts whatever follows it on top of
    the second line.
    """
    chars_per_line = max(int((width_in * 72.0) / (pt * (adv or ADV_BODY))), 1)
    return sum(max(1, -(-len(seg) // chars_per_line))
               for seg in (text or "").split("\n")) or 1


def _display_block(text: str, width_in: float, pt: float) -> float:
    """Height in inches a display-font run occupies, leading included."""
    return _wrapped_lines(text, width_in, pt, ADV_DISPLAY) * (pt * 1.32) / 72.0


def _fit(text: str, width_in: float, base: float, min_pt: float,
         max_lines: int) -> float:
    """Step a display size down until it wraps within `max_lines`. Episode
    titles are not written to fit a slide, so the cover has to give."""
    pt = base
    while pt > min_pt and _wrapped_lines(text, width_in, pt,
                                         ADV_DISPLAY) > max_lines:
        pt -= 3.0
    return pt


# --- shared furniture ------------------------------------------------------

def _chrome(slide, s, dark=False):
    """Eyebrow left, meta right, on one baseline at the top of the slide."""
    muted = DARK_MUTED if dark else MUTED
    eyebrow = (s.get("eyebrow") or "").strip()
    meta = (s.get("meta") or "").strip()
    if eyebrow:
        tf = _txt(slide, PAD_X, Y_CHROME, COL_W * 0.62, 0.3)
        p = _para(tf, True)
        _run(p, eyebrow, FONT_MONO, T_EYEBROW, muted, upper=True,
             track=TRACK_EYEBROW)
    if meta:
        tf = _txt(slide, PAD_X + COL_W * 0.62, Y_CHROME, COL_W * 0.38, 0.3)
        p = _para(tf, True)
        _run(p, meta, FONT_MONO, T_EYEBROW, muted, upper=True,
             align=PP_ALIGN.RIGHT, track=TRACK_EYEBROW)


# Letter-spacing, in em, for the uppercase mono labels. An untracked
# uppercase mono eyebrow is one of the clearer tells that a deck was set by a
# machine; these are the source system's own values.
TRACK_EYEBROW = 0.20
TRACK_LABEL = 0.16
TRACK_MICRO = 0.14


def _rule(slide, y, width=1.1, colour=METAL, thickness=0.014):
    _rect(slide, PAD_X, y, width, thickness, colour)


def _foot(slide, s, dark=False):
    """Hairline, a pop dot, and the footer label. The dot is where the deck
    spends its second colour."""
    label = (s.get("footer_l") or "").strip()
    line_c = DARK_LINE if dark else LINE
    muted = DARK_MUTED if dark else MUTED
    _rect(slide, PAD_X, Y_FOOT, COL_W, 0.01, line_c)
    if not label:
        return
    _dot(slide, PAD_X, Y_FOOT + 0.19, 0.073, POP)
    tf = _txt(slide, PAD_X + 0.22, Y_FOOT + 0.15, COL_W - 0.22, 0.3)
    p = _para(tf, True)
    _run(p, label, FONT_MONO, T_MICRO, muted, upper=True, track=TRACK_MICRO)


def _eyebrow_at(slide, text, y, dark=False):
    if not (text or "").strip():
        return
    tf = _txt(slide, PAD_X, y, COL_W, 0.28)
    p = _para(tf, True)
    _run(p, text, FONT_MONO, T_EYEBROW, DARK_MUTED if dark else MUTED,
         upper=True, track=TRACK_EYEBROW)


def _heading(slide, text, y=Y_HEAD, size=T_H1, colour=INK, width=None,
             max_lines=2):
    """Draws the heading and returns the y it ended at. Callers place their
    rule and body from that return value, never from a fixed slot: a heading
    that wraps to two lines otherwise runs straight through both."""
    if not (text or "").strip():
        return y
    w = width or COL_W
    pt = _fit(text, w, size, 26.0, max_lines)
    h = _display_block(text, w, pt)
    tf = _txt(slide, PAD_X, y, w, h + 0.2)
    p = _para(tf, True)
    _run(p, text, FONT_DISPLAY, pt, colour, bold=True)
    return y + h


def _head_block(slide, s, key="heading", width=None):
    """Heading, then the hairline under it. Returns the body baseline."""
    bottom = _heading(slide, s.get(key), width=width)
    rule_y = max(Y_RULE, bottom + 0.16)
    _rule(slide, rule_y)
    return rule_y + 0.28


def _lede(slide, text, y, width=None, colour=MUTED, size=T_BODY):
    if not (text or "").strip():
        return
    tf = _txt(slide, PAD_X, y, width or COL_W * 0.62, 1.1)
    p = _para(tf, True)
    _run(p, text, FONT_BODY, size, colour)


def _bullets(slide, points, x, y, w, dark=False, label_pt=T_BODY,
             sub_pt=T_SMALL, gap=0.30):
    """Stacked rows measured cumulatively, so a label that wraps pushes the
    next row down instead of being overprinted by it."""
    ink = DARK_INK if dark else INK
    muted = DARK_MUTED if dark else MUTED
    cur = y
    for pt_item in points or []:
        label = pt_item.get("label", "")
        sub = pt_item.get("sub", "")
        lab_lines = _wrapped_lines(label, w - 0.34, label_pt)
        lab_h = lab_lines * (label_pt * 1.32) / 72.0
        _rect(slide, x, cur + 0.055, 0.02, lab_h - 0.04, ACCENT if not dark
              else DARK_ACCENT)
        tf = _txt(slide, x + 0.28, cur, w - 0.34, lab_h)
        p = _para(tf, True)
        _run(p, label, FONT_BODY, label_pt, ink, bold=True)
        cur += lab_h + 0.04
        if sub:
            sub_lines = _wrapped_lines(sub, w - 0.34, sub_pt)
            sub_h = sub_lines * (sub_pt * 1.42) / 72.0
            tf = _txt(slide, x + 0.28, cur, w - 0.34, sub_h)
            p = _para(tf, True)
            _run(p, sub, FONT_BODY, sub_pt, muted)
            cur += sub_h
        cur += gap
    return cur


# --- dark slides -----------------------------------------------------------

def _cover(slide, s):
    _bg(slide, DARK)
    _eyebrow_at(slide, s.get("eyebrow"), 0.86, dark=True)
    title = s.get("title", "")
    w = COL_W * 0.88
    pt = _fit(title, w, T_COVER, 34.0, 3)
    h = _display_block(title, w, pt)
    tf = _txt(slide, PAD_X, 2.15, w, h + 0.2)
    p = _para(tf, True)
    _run(p, title, FONT_DISPLAY, pt, DARK_INK, bold=True)
    _rule(slide, 2.15 + h + 0.42, width=1.4, colour=DARK_ACCENT)
    _lede(slide, s.get("lede"), 2.15 + h + 0.70, width=COL_W * 0.66,
          colour=DARK_MUTED)


def _closing(slide, s):
    _bg(slide, DARK)
    _eyebrow_at(slide, s.get("eyebrow"), 0.86, dark=True)
    bottom = _heading(slide, s.get("heading"), y=2.55, size=T_DISPLAY,
                      colour=DARK_INK, width=COL_W * 0.82)
    _rule(slide, bottom + 0.34, width=1.4, colour=DARK_ACCENT)
    _lede(slide, s.get("cta"), bottom + 0.62, width=COL_W * 0.62,
          colour=DARK_MUTED)
    meta = (s.get("meta") or "").strip()
    if meta:
        tf = _txt(slide, PAD_X, Y_FOOT + 0.15, COL_W, 0.3)
        p = _para(tf, True)
        _run(p, meta, FONT_MONO, T_MICRO, DARK_MUTED, upper=True,
             track=TRACK_MICRO)
        _rect(slide, PAD_X, Y_FOOT, COL_W, 0.01, DARK_LINE)


def _divider(slide, s):
    _bg(slide, DARK)
    _chrome(slide, s, dark=True)
    _eyebrow_at(slide, s.get("eyebrow"), 2.5, dark=True)
    bottom = _heading(slide, s.get("title"), y=2.85, size=T_DISPLAY,
                      colour=DARK_INK, width=COL_W * 0.8)
    _rule(slide, bottom + 0.30, width=1.1, colour=DARK_ACCENT)
    _lede(slide, s.get("lede"), bottom + 0.58, width=COL_W * 0.6,
          colour=DARK_MUTED)


def _full_bleed(slide, s):
    """The deck's one polychrome moment: a cobalt field, paper text, nothing
    else on it. Kept to a single slide by training.py, which is why it can
    afford to be this loud."""
    _bg(slide, ACCENT)
    _eyebrow_at(slide, s.get("eyebrow"), 0.86, dark=True)
    heading = s.get("heading", "")
    w = COL_W * 0.84
    pt = _fit(heading, w, T_DISPLAY, 34.0, 3)
    h = _display_block(heading, w, pt)
    tf = _txt(slide, PAD_X, 2.3, w, h + 0.2)
    p = _para(tf, True)
    _run(p, heading, FONT_DISPLAY, pt, DARK_INK, bold=True)
    _lede(slide, s.get("lede"), 2.3 + h + 0.46, width=COL_W * 0.62,
          colour="D6E0F0")
    meta = (s.get("meta") or "").strip()
    if meta:
        tf = _txt(slide, PAD_X, Y_FOOT + 0.15, COL_W, 0.3)
        p = _para(tf, True)
        _run(p, meta, FONT_MONO, T_MICRO, "D6E0F0", upper=True,
             track=TRACK_MICRO)


# --- light slides ----------------------------------------------------------

def _content(slide, s):
    _bg(slide, PAPER)
    _chrome(slide, s)
    body = _head_block(slide, s)
    _bullets(slide, s.get("points"), PAD_X, body, COL_W * 0.78)
    _foot(slide, s)


def _content_stat(slide, s):
    _bg(slide, PAPER)
    _chrome(slide, s)
    body = _head_block(slide, s, width=COL_W * 0.60)
    _bullets(slide, (s.get("points") or [])[:3], PAD_X, body, COL_W * 0.55)
    hero = s.get("hero_stat") or {}
    num = str(hero.get("num", "")).strip()
    if not num:
        _foot(slide, s)
        return
    x = PAD_X + COL_W * 0.63
    w = COL_W * 0.37
    _rect(slide, x - 0.34, Y_HEAD, 0.012, 4.0, LINE)
    tf = _txt(slide, x, Y_HEAD + 0.55, w, 1.5)
    p = _para(tf, True)
    fam, bd = _num()
    _run(p, num, fam, T_STAT * 0.72, ACCENT, bold=bd)
    tf = _txt(slide, x, Y_HEAD + 1.85, w, 0.4)
    p = _para(tf, True)
    _run(p, hero.get("label", ""), FONT_MONO, T_EYEBROW, MUTED,
         upper=True, track=TRACK_LABEL)
    desc = (hero.get("desc") or "").strip()
    if desc:
        tf = _txt(slide, x, Y_HEAD + 2.30, w, 1.4)
        p = _para(tf, True)
        _run(p, desc, FONT_BODY, T_SMALL, MUTED)
    _foot(slide, s)


def _data(slide, s):
    """Left-anchored hero numeral at 8x body size, then a rule, then at most
    two receding satellites. The scale jump is the whole design."""
    _bg(slide, PAPER)
    _chrome(slide, s)
    _eyebrow_at(slide, s.get("rail_label"), 1.20)
    hero = s.get("hero_stat") or {}
    num = str(hero.get("num", "")).strip()
    tf = _txt(slide, PAD_X, 1.60, COL_W * 0.8, 1.7)
    p = _para(tf, True)
    fam, bd = _num()
    _run(p, num, fam, T_STAT, ACCENT, bold=bd)
    label = (hero.get("label") or "").strip()
    if label:
        pt = _fit(label, COL_W * 0.7, T_H1, 26.0, 1)
        tf = _txt(slide, PAD_X, 3.30, COL_W * 0.7, 1.1)
        p = _para(tf, True)
        _run(p, label, FONT_DISPLAY, pt, INK, bold=True)
    _rule(slide, 4.50)
    desc = (hero.get("desc") or "").strip()
    if desc:
        tf = _txt(slide, PAD_X, 4.72, COL_W * 0.52, 1.0)
        p = _para(tf, True)
        _run(p, desc, FONT_BODY, T_BODY, MUTED)
    x = PAD_X + COL_W * 0.60
    for st in (s.get("stats") or [])[:2]:
        tf = _txt(slide, x, 4.55, 2.2, 0.7)
        p = _para(tf, True)
        fam, bd = _num()
        _run(p, str(st.get("num", "")), fam, T_SAT, INK, bold=bd)
        tf = _txt(slide, x, 5.15, 2.2, 0.5)
        p = _para(tf, True)
        _run(p, st.get("label", ""), FONT_MONO, T_MICRO, MUTED,
             upper=True, track=TRACK_LABEL)
        x += 2.5
    _foot(slide, s)


def _two_column(slide, s):
    _bg(slide, PAPER)
    _chrome(slide, s)
    _heading(slide, s.get("heading"), max_lines=1)
    _lede(slide, s.get("lede"), 2.42, width=COL_W * 0.7)
    top, panel_h = 2.98, 3.52
    panel_w = (COL_W - 0.5) / 2
    for i, side in enumerate((s.get("left") or {}, s.get("right") or {})):
        x = PAD_X + i * (panel_w + 0.5)
        _rect(slide, x, top, panel_w, panel_h, PANEL)
        _rect(slide, x, top, panel_w, 0.032, ACCENT if i == 0 else METAL)
        tf = _txt(slide, x + 0.28, top + 0.26, panel_w - 0.56, 0.4)
        p = _para(tf, True)
        _run(p, side.get("heading", ""), FONT_MONO, T_EYEBROW, INK,
             upper=True, track=TRACK_EYEBROW)
        _bullets(slide, side.get("points"), x + 0.28, top + 0.72,
                 panel_w - 0.56, label_pt=T_SMALL, sub_pt=T_MICRO,
                 gap=0.14)
    _foot(slide, s)


def _process(slide, s):
    _bg(slide, PAPER)
    _chrome(slide, s)
    body = _head_block(slide, s)
    steps = s.get("steps") or []
    dominant = s.get("dominant", 0)
    n = max(len(steps), 1)
    gap = 0.34
    w = (COL_W - gap * (n - 1)) / n
    for i, st in enumerate(steps):
        x = PAD_X + i * (w + gap)
        on = i == dominant
        _rect(slide, x, body + 0.02, w, 2.55, PANEL if on else PAPER)
        _rect(slide, x, body + 0.02, w, 0.032, ACCENT if on else LINE)
        tf = _txt(slide, x + 0.22, body + 0.24, w - 0.44, 0.5)
        p = _para(tf, True)
        fam, bd = _num(on)
        _run(p, f"{i + 1:02d}", fam, T_SAT, ACCENT if on else MUTED, bold=bd)
        tf = _txt(slide, x + 0.22, body + 0.82, w - 0.44, 0.9)
        p = _para(tf, True)
        _run(p, st.get("label", ""), FONT_BODY, T_BODY, INK, bold=True)
        sub = (st.get("sub") or "").strip()
        if sub:
            lines = _wrapped_lines(st.get("label", ""), w - 0.44, T_BODY)
            tf = _txt(slide, x + 0.22, body + 0.82 + lines * 0.24 + 0.12,
                      w - 0.44, 1.1)
            p = _para(tf, True)
            _run(p, sub, FONT_BODY, T_SMALL, MUTED)
    _foot(slide, s)


def _agenda(slide, s):
    _bg(slide, PAPER)
    _chrome(slide, s)
    body = _head_block(slide, s, key="title")
    items = s.get("items") or []
    active = s.get("active")
    cur = body
    for i, it in enumerate(items):
        on = active == i
        label = it.get("label", "")
        lines = _wrapped_lines(label, COL_W * 0.62, T_BODY)
        h = lines * 0.26 + 0.10
        if on:
            _rect(slide, PAD_X - 0.18, cur - 0.05, COL_W * 0.72, h + 0.14,
                  PANEL)
            _rect(slide, PAD_X - 0.18, cur - 0.05, 0.032, h + 0.14, ACCENT)
        tf = _txt(slide, PAD_X, cur, 0.6, 0.35)
        p = _para(tf, True)
        fam, bd = _num(on)
        _run(p, f"{i + 1:02d}", fam, T_SMALL, ACCENT if on else MUTED, bold=bd)
        tf = _txt(slide, PAD_X + 0.72, cur - 0.03, COL_W * 0.60, h)
        p = _para(tf, True)
        _run(p, label, FONT_BODY, T_BODY, INK, bold=on)
        sub = (it.get("sub") or "").strip()
        if sub:
            tf = _txt(slide, PAD_X + 0.72 + COL_W * 0.62, cur - 0.01,
                      COL_W * 0.30, h)
            p = _para(tf, True)
            _run(p, sub, FONT_BODY, T_SMALL, MUTED)
        cur += h + 0.20
    _foot(slide, s)


def _quote(slide, s):
    _bg(slide, PANEL)
    _chrome(slide, s)
    quote = (s.get("quote") or "").strip()
    top, w = 2.05, COL_W * 0.80
    pt = _fit(quote, w, T_H1, 24.0, 4)
    block_h = _display_block(quote, w, pt)
    tf = _txt(slide, PAD_X + 0.42, top, w, block_h + 0.3)
    p = _para(tf, True)
    _run(p, f"“{quote}”", FONT_DISPLAY, pt, INK, bold=True)
    _rect(slide, PAD_X, top + 0.10, 0.032, max(block_h - 0.1, 0.4), ACCENT)
    attribution = (s.get("attribution") or "").strip()
    if attribution:
        tf = _txt(slide, PAD_X + 0.42, top + block_h + 0.34, COL_W * 0.7, 0.4)
        p = _para(tf, True)
        _run(p, attribution, FONT_MONO, T_EYEBROW, MUTED, upper=True,
             track=TRACK_MICRO)


def _callout(slide, s):
    """A single panel sized to what it holds. A fixed-height panel is fine
    until a long lede runs out through its bottom edge, which is exactly what
    a callout -- the slide whose whole job is one framed statement -- cannot
    afford to do."""
    _bg(slide, PAPER)
    _chrome(slide, s)
    top, pad = 2.10, 0.42
    heading = s.get("heading", "")
    lede = (s.get("lede") or "").strip()
    hw = COL_W - 1.1
    pt = _fit(heading, hw, T_H1, 26.0, 2)
    head_h = _display_block(heading, hw, pt)
    lede_w = COL_W * 0.72
    lede_h = (_wrapped_lines(lede, lede_w, T_BODY) * (T_BODY * 1.42) / 72.0
              if lede else 0.0)
    gap = 0.30 if lede else 0.0
    panel_h = min(pad * 2 + head_h + gap + lede_h, Y_FOOT - 0.30 - top)
    _rect(slide, PAD_X, top, COL_W, panel_h, PANEL)
    _rect(slide, PAD_X, top, 0.042, panel_h, POP)
    tf = _txt(slide, PAD_X + 0.55, top + pad, hw, head_h + 0.2)
    p = _para(tf, True)
    _run(p, heading, FONT_DISPLAY, pt, INK, bold=True)
    if lede:
        tf = _txt(slide, PAD_X + 0.55, top + pad + head_h + gap, lede_w,
                  lede_h + 0.2)
        p = _para(tf, True)
        _run(p, lede, FONT_BODY, T_BODY, MUTED)
    _foot(slide, s)


def _chart(slide, s):
    _bg(slide, PAPER)
    _chrome(slide, s)
    body = _head_block(slide, s)
    data = s.get("data") or []
    highlight = s.get("highlight", 0)
    unit = (s.get("unit") or "").strip()
    top = max((d.get("value", 0) for d in data), default=1.0) or 1.0
    label_w, track_w = 3.1, COL_W - 3.1 - 1.5
    row_h = min(0.62, (Y_FOOT - 0.30 - body) / max(len(data), 1))
    cur = body + 0.12
    for i, d in enumerate(data):
        on = i == highlight
        tf = _txt(slide, PAD_X, cur + 0.02, label_w - 0.25, row_h,
                  MSO_ANCHOR.MIDDLE)
        p = _para(tf, True)
        _run(p, d.get("label", ""), FONT_BODY, T_SMALL, INK if on else MUTED,
             bold=on)
        frac = max(float(d.get("value", 0)) / float(top), 0.0)
        bar_h = row_h * 0.44
        _rect(slide, PAD_X + label_w, cur + (row_h - bar_h) / 2, track_w, bar_h,
              LINE)
        if frac > 0:
            _rect(slide, PAD_X + label_w, cur + (row_h - bar_h) / 2,
                  max(track_w * frac, 0.02), bar_h, ACCENT if on else "AEB2B6")
        tf = _txt(slide, PAD_X + label_w + track_w + 0.18, cur + 0.02, 1.3,
                  row_h, MSO_ANCHOR.MIDDLE)
        p = _para(tf, True)
        val = d.get("value", 0)
        shown = f"{val:g}{unit}" if unit else f"{val:g}"
        fam, bd = _num(on)
        _run(p, shown, fam, T_SMALL, ACCENT if on else MUTED, bold=bd)
        cur += row_h
    _foot(slide, s)


def _scorecard(slide, s):
    """Three chips per row, n filled. training.py ships every row at level 0 on
    purpose — the ratings belong to the room running the session, not to the
    episode — so an all-empty scorecard is correct, not a bug."""
    _bg(slide, PAPER)
    _chrome(slide, s)
    body = _head_block(slide, s)
    rows = s.get("rows") or []
    row_h = min(0.66, (Y_FOOT - 0.30 - body) / max(len(rows), 1))
    cur = body + 0.10
    chip_w, chip_gap = 0.30, 0.10
    for row in rows:
        level = int(row.get("level", 0) or 0)
        tf = _txt(slide, PAD_X, cur, COL_W * 0.46, row_h, MSO_ANCHOR.MIDDLE)
        p = _para(tf, True)
        _run(p, row.get("label", ""), FONT_BODY, T_BODY, INK, bold=True)
        x = PAD_X + COL_W * 0.48
        for k in range(3):
            filled = k < level
            _rect(slide, x, cur + row_h / 2 - 0.07, chip_w, 0.14,
                  ACCENT if filled else LINE)
            x += chip_w + chip_gap
        note = (row.get("note") or "").strip()
        if note:
            tf = _txt(slide, PAD_X + COL_W * 0.62, cur, COL_W * 0.38, row_h,
                      MSO_ANCHOR.MIDDLE)
            p = _para(tf, True)
            _run(p, note, FONT_BODY, T_SMALL, MUTED)
        _rect(slide, PAD_X, cur + row_h - 0.02, COL_W, 0.008, LINE)
        cur += row_h
    _foot(slide, s)


WRITERS = {
    "cover": _cover, "closing": _closing, "divider": _divider,
    "full_bleed": _full_bleed, "content": _content,
    "content_stat": _content_stat, "data": _data, "two_column": _two_column,
    "process": _process, "agenda": _agenda, "quote": _quote,
    "callout": _callout, "chart": _chart, "scorecard": _scorecard,
}

THEMES = ("studio",)


def render(slides: list[dict], pptx_path: str) -> None:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(SW_IN), Inches(SH_IN)
    blank = prs.slide_layouts[6]
    for s in slides:
        kind = s.get("kind")
        fn = WRITERS.get(kind)
        if fn is None:
            raise KeyError(kind)
        slide = prs.slides.add_slide(blank)
        fn(slide, s)
        notes = (s.get("notes") or "").strip()
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    prs.save(pptx_path)
