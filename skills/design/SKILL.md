---
name: design
description: >
  Turn a PASSed Sori brief into a deck through the configured design
  backend: a Claude Design Slides artifact with the owner's design system,
  the d_sign HTML masters, the offline python-pptx renderer, or a hand-off
  package for ChatSlide or Figma Slides. Use when the user says: design the
  deck, build the slides from the brief, make it in Claude Design, export for
  ChatSlide, set the design backend, /sori:design. Not for writing the brief
  (/sori:curate) or the one-shot outline route (/sori:train).
---

# Sori: design (brief → deck)

`SORI` below is the folder that holds `sori.py`: `${CLAUDE_PLUGIN_ROOT}`
when installed as a plugin, otherwise a checkout of
https://github.com/onepromptman/sori-app. `python3` may be `python` or `py`
on Windows.

## Preconditions

The episode folder (`~/Sori/Trainings/<Show>/<date> - <title>/`) holds a
`brief.md` and a `critique.md` whose verdict is `PASS`. No critique, or
`REVISE`: send the user to `/sori:curate` first. `sori.py design` also
refuses a brief that fails the sourcing gate, whatever the critique says.

## Backend

```bash
python3 "$SORI/sori.py" design-config                       # show
python3 "$SORI/sori.py" design-config design_backend <offline|claude-design|dsign-html|chatslide|figma>
python3 "$SORI/sori.py" design-config design_system_url <https://claude.ai/artifact/...>
python3 "$SORI/sori.py" design-config dsign_root <path to a d_sign checkout>
python3 "$SORI/sori.py" design-config dsign_theme <nok|baek|jeok>
```

`offline` is the default and what a public install can always do.
`claude-design` is the owner's route: one design system, picked once. The
others are hand-offs. `--backend` on a single run overrides the setting.

## Run

```bash
python3 "$SORI/sori.py" design "<episode folder>" [--backend ...] --episode-id "<id>" --show "<show>"
```

This writes `handoff/<backend>/` (brief, verbatim evidence, a README of
exact steps, backend extras) and, for `offline` with an `outline.json`
present, renders the `.pptx` and study guide and records `rendered`.

Then delegate to the **deck-designer** agent with the hand-off folder. It
follows the README for that backend, builds the deck, and records
`designed` (or `rendered`) in the ledger with the URL or path. For
`claude-design` the artifact is private to the owner; for `chatslide` the
upload is the user's step and the agent only prepares and records.

## Report

The deck's location (URL or path), the backend, the slide count, and the
ledger row. If the user wants the takeaways, point at `brief.md` or the
study guide, not a summary from memory.

## Never

- Change a quote or add a number that is not under the brief's Evidence.
- Build a deck for a brief without a `PASS` critique.
- Share, publish or post a deck anywhere; the owner does that.
- Mix two palette modes in one deck, on any backend.
