# Which design system is which (and which one Sori should render with)

Four things carry the BH·SEOUL name or look. They are not the same system,
and Sori's vendored engine is the stale one. This page says what each is,
how they relate, and what the pipeline points at.

| | What it is | Themes / modes | Canonical? | Where |
|---|---|---|---|---|
| **d_sign** (`recruitaib/d_sign`) | The BH·SEOUL **deck** design system, v4. 87 HTML slide masters (20 base + 9 variety per theme) over one `tokens/theme.css`, three theme worlds on a `[data-mode]` switch, a decision ledger (`REGISTRY.md`), a base-lock checksum gate, render/PDF scripts, and `cards/` compiled as `@dsCard` files for Claude Design. The "Kreate" system. | **nok 녹 / baek 백 / jeok 적** | **Yes.** `README.md`: "the ONE system". | d_sign repo root; published to Claude Design as "AI Training Decks — BH · SEOUL" (`claude.ai/artifact/2b8zzaic9C6cfKDUYtW9fV`) |
| **Sori `engine/deckgen.py`** | A python-pptx renderer copied from `ai-group-training/_development/tools/deckgen.py` (2026-06-26). Its palettes are the **pre-v4** look: `light` (hanji `#F5F2EC` / cheong blue), `dark`, `dancheong`. d_sign's README retires exactly these: "the pre-v4 light/dark/dancheong system ... is retired". | light (shown as `baek`) / dark / dancheong | **No.** Stale since 2026-07-02. | `sori/engine/` (private checkout only) |
| **chimera `bh-seoul`** | The BH·SEOUL **UI** system: semantic `--bh-*` tokens for web surfaces, WCAG contract. Shares the words baek/jeok with d_sign's deck themes but is a different law (`d_sign/DISAMBIGUATION.md`: deck-baek vs ui-baek; hue anchors flow deck → ui, never back). | light · dark · taegeuk · sumook · dancheong · baek · jeok | Canonical for UI, not for decks. | `chimera/design-system/bh-seoul` |
| **Sori `themes/studio.py`** | Sori's public, unbranded pptx theme: stock fonts (Georgia / Segoe UI / Consolas), eight colours. Exists so a public install renders decks that open the same on any machine with nothing installed. | studio | Canonical for the public plugin's offline backend. | `sori/themes/` |

Also in Bryan's Claude Design account, as separate design systems:
AI-maxxing, Bryan / RecOps, Kreate (the d_sign system under its approved
name), Redact V1, Ulysses Talent, Vermillion. "The real design system is a
consolidation": d_sign already *is* the consolidation for decks (it
harvested `seoul`, `b-all` and the chimera fork, and froze the base on
2026-07-06); the remaining systems are per-client looks, not inputs to it.

## What this means for Sori

1. **Decks for the owner render with d_sign, not the engine.** The
   `claude-design` backend attaches "AI Training Decks — BH · SEOUL"; the
   `dsign-html` backend builds from the masters. The engine's `baek` is
   not deck-baek; it is the retired light mode wearing the name.
2. **The engine stays only as the exe's offline renderer** until a
   d_sign-based HTML renderer replaces it. Refreshing it by copy, as
   `engine/README.md` says, would copy a retired look; do not.
3. **`studio` stays the public default.** It is the one theme that needs no
   fonts, no checkout and no account.
4. **Pipeline settings name the system explicitly** (`design_system_url`,
   `dsign_root`, `dsign_theme`), so the agent never guesses which of the
   seven systems to attach. Per chimera's `design-publish` rule, nothing is
   auto-selected.

## The d_sign masters, for the `dsign-html` backend

Masters live at `themes/<theme>/<layout>.html`, one file per layout, each
linking `../../tokens/theme.css` and its theme's own pattern and seal art
under `assets/<theme>/`. A deck is built by copying a master's CSS
verbatim and swapping content (`decks/m00-agentic-ai-fundamentals/BUILD-NOTES.md`
is the exemplar: 21 slides, a `player.html`, gates for mode purity and
content fidelity). `pipeline/design.py` maps brief slide kinds to layouts:

| brief kind | d_sign master |
|---|---|
| cover / closing / divider | `title` / `closing` / `divider` |
| content / content_stat / two_column | `content` / `content-stat` / `twocol` |
| quote / callout / manifesto / full_bleed | `quote` / `manifesto` / `manifesto` / `full-bleed` |
| process / steps / exercise / timeline | `process` / `steps` / `steps` / `timeline` |
| agenda / data / stat / chart / scorecard / code | `agenda` / `data` / `stat` / `data` / `framework` / `code` |

The base is frozen (`scripts/gates/verify-base-lock.mjs`); a deck never
edits a master, it copies. Export: `node scripts/export-pdf.mjs` or
`render.mjs`; every slide file is already a `@dsCard` for Claude Design.

## Open question for Bryan

Whether to build the HTML renderer in Sori (brief → d_sign slides without an
agent hand-building each file). It needs the masters' content slots to be
stable, which `REGISTRY.md`'s base lock suggests they now are. Until then
`dsign-html` is an agent-executed hand-off, which is how every d_sign deck
has been built so far.
