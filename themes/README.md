# themes/ — bring your own design system

Sori ships one theme, **`studio`**: an unbranded editorial deck in fonts a
stock Windows install already has. Your slides should look like *your*
organisation's slides, not like ours, so the renderer is a swappable file
rather than something baked into the tool.

```
themes/
  studio.py     the default. ~640 lines. Copy this to start.
  README.md     you are here
```

## Fonts: nothing to install

`studio` names Georgia, Segoe UI and Consolas — faces a stock machine already
has. That is a deliberate constraint, not a compromise. **OOXML stores one
font *name* per run, has no fallback chain, and python-pptx cannot embed a
face**, so naming a font the opening machine lacks does not fall back to your
second choice: PowerPoint substitutes its own default and the deck arrives
looking broken. Bundling and installing faces makes a deck right on the
machine that rendered it and wrong on every machine it is forwarded to.

Georgia carries every headline and ships on Windows and macOS both. On a
Mac-first audience, swap `FONT_BODY` to `Helvetica Neue` and `FONT_MONO` to
`Menlo`.

If you do point a theme at a font your audience may not have, either tell
them to install it or use PowerPoint's *File → Options → Save → Embed fonts
in the file* before sending. Exported PDFs are safe either way — they carry
their glyphs.

## The contract

A theme backend is a Python module that exports two names:

```python
THEMES = ("mytheme",)   # names you offer; deck_render reads this

def render(slides: list[dict], pptx_path: str) -> None:
    """Paint `slides` into a .pptx at `pptx_path`."""
```

That is the whole interface. `deck_render.py` builds the slide list and hands
it over; what you do with python-pptx after that is yours.

## Fastest path: change six colours

Most people do not need a new file. Open `studio.py` and edit the palette and
the three font names at the top:

```python
PAPER  = "F7F7F4"   # light slide ground -- warm, not #FFFFFF
PANEL  = "ECECE6"   # raised panels, quote ground
INK    = "14171C"   # body + headings -- cool, not #000000
MUTED  = "6F7172"   # secondary text (pre-blended against PAPER)
LINE   = "D7D8D6"   # hairlines, empty chart track
METAL  = "C9A24B"   # rules and structure. Never text.
ACCENT = "0B4DA2"   # THE load-bearing colour
POP    = "C8202E"   # spent once or twice a deck. Never body text.

DARK        = "14171C"   # cover / section break / closing ground
DARK_ACCENT = "C9A24B"   # ACCENT is unreadable on DARK, so gold takes over

FONT_DISPLAY = "Georgia"    # headings
FONT_BODY    = "Segoe UI"   # body copy
FONT_MONO    = "Consolas"   # eyebrows, figures, labels
```

Use fonts your audience actually has installed. PowerPoint substitutes
silently, and a substituted font is how a deck ends up looking broken on
someone else's laptop. The three above are stock Windows; on a Mac-first
audience swap `Segoe UI` for `Helvetica Neue` and `Consolas` for `Menlo`.

## Two things worth keeping if you rewrite it

**The type scale has two anchors and nothing between them** -- a display size
and a body size. Reaching for a mid-sized subhead is the single clearest tell
that a deck was generated rather than set, so `studio.py` does not define one.

**Nothing sits at a fixed y below a heading.** python-pptx cannot measure
text, so `_display_block()` estimates how tall a run will be and every rule,
panel and body block is placed from that estimate rather than from a constant.
Estimate optimistically and the next block silently prints on top of the last
one -- which is what an over-eager average character width will do to you.

## Writing a real backend

1. Copy `studio.py` to `themes/mytheme.py`.
2. Set `THEMES = ("mytheme",)`.
3. Register it in `deck_render.py` next to the `studio` import.

Your `render()` receives one dict per slide. Every dict has `kind` and
`notes`; the rest depends on the kind:

| `kind` | Fields |
|---|---|
| `cover` | `title`, `lede`, `eyebrow` |
| `closing` | `heading`, `cta`, `eyebrow`, `meta` |
| `divider` | `title`, `eyebrow`, `lede`, `meta` |
| `content` | `heading`, `eyebrow`, `meta`, `points[{label,sub}]`, `footer_l`, `footer_r` |
| `content_stat` | as `content`, plus `hero_stat{num,label,desc}` (max 3 points) |
| `two_column` | `eyebrow`, `left{heading,points}`, `right{heading,points}` |
| `process` | `heading`, `eyebrow`, `steps[{label,sub}]`, `dominant` (index) |
| `agenda` | `title`, `eyebrow`, `meta`, `items[{label,sub}]`, `active` (index or None) |
| `quote` | `quote`, `attribution`, `eyebrow` |
| `callout` | `heading`, `eyebrow`, `lede` |
| `full_bleed` | `heading`, `eyebrow`, `lede`, `meta` — the deck's one statement slide |
| `data` | `eyebrow`, `rail_label`, `hero_stat{num,label,desc}`, `stats[]` (max 2) |
| `scorecard` | `heading`, `eyebrow`, `meta`, `rows[{label,level 0-3,note}]` |
| `chart` | `heading`, `eyebrow`, `meta`, `chart_type`, `data[{label,value}]`, `unit`, `highlight` |

Raise `KeyError(kind)` for anything you do not handle and `deck_render` turns
it into a clean error instead of a traceback.

Slides also carry a `mode` string (the theme name, or the private engine's
palette name). `studio` ignores it -- it picks its own dark grounds for the
cover, section breaks and closing -- but use it if your backend has variants.

## Why the numbers are the way they are

Sori writes the outline from a transcript, and the rules that govern it live
in `training.py`, not here: a `hero_stat` must be a figure literally stated in
the episode, a `chart` needs at least three such figures sharing one unit, and
a `scorecard` ships every row at level 0 because those ratings belong to the
room, not to the podcast. A theme can restyle any of it; a theme should not
invent a value that was not passed in.
