---
name: train
description: >
  Turn a Sori transcript (.txt) into a training deck (.pptx) plus a
  study guide (.md). Default route is free: you (the session) write the deck
  outline from the transcript against Sori's rules, and train.py renders it
  locally, no API key. The optional API route makes one paid Claude call on
  the user's own key. Use when the user says: make a training / deck /
  slides / study guide from this transcript, train this episode, generate
  training, /sori:train. Not for getting the transcript (/sori:transcribe or
  /sori:sweep) or saving an API key (/sori:shows).
---

# Sori: training deck from a transcript

`SORI` below is the folder that holds `train.py`: `${CLAUDE_PLUGIN_ROOT}`
when installed as a plugin, otherwise the current checkout of
https://github.com/onepromptman/sori-app. On Windows, `python` may be `py`.
Setup, once: `cd "$SORI" && python -m pip install -r requirements-app.txt`
(adds `python-pptx`, `numpy`, `matplotlib`; `anthropic` is only used by the
paid route).

Two routes, one engine. Both end in the same validator and renderer, so the
deck is the same deck whoever authored the outline. The exe uses the API
route; from a Claude session the outline route is the default because you
are already the model.

## Route 1 (default, free): you write the outline, train.py renders it

1. Read the rules and the exact JSON shape:

   ```bash
   python "$SORI/train.py" --brief
   ```

   The brief is Sori's system prompt (five house rules: every claim, quote
   and number from the transcript; no forced hero_stat; concrete examples;
   terse slides; the study guide is the fuller version) plus the
   `submit_training` schema: `deck_title`, optional `deck_subtitle`,
   `closing_heading`, `cta`, 6 to 20 `slides` of kinds `divider`, `content`,
   `content_stat`, `two_column`, `process`, `agenda`, `quote`, `callout`,
   and `study_guide_markdown`.

2. Read the whole transcript file. Do not write from memory of the show.
   Skip ad reads. If the transcript is thin (see the wpm check in
   `/sori:transcribe`), say so before building.

3. Write `outline.json` next to the transcript, following the brief. A
   `hero_stat` must be a number literally stated in the transcript; a
   `quote` must be verbatim. Put speaker notes in `notes`.

4. Render:

   ```bash
   python "$SORI/train.py" "<transcript.txt>" --outline outline.json [--out <folder>] [--theme baek|dark|dancheong]
   ```

   Exit 1 with `!! ...` on stderr means the outline failed validation (slide
   count, unknown kind, empty quote, missing study guide); fix the JSON and
   rerun. Nothing is spent on this route, ever.

## Route 2 (paid): one Claude API call on the user's key

Use only when the user asks for the API route explicitly (for parity with
the exe, or to compare output). Every run is one billed call, roughly the
transcript's size in input tokens (capped by `MAX_TRANSCRIPT_CHARS` in
`training.py`) plus a few thousand output tokens.

1. Confirm the user wants to spend it, once per run.
2. Confirm a key is reachable: `ANTHROPIC_API_KEY` in the environment, else
   the key saved by the Sori app or `settings.py api-key set`
   (`%USERPROFILE%\Sori\credentials.json`; `SORI_HOME` overrides). No key:
   stop and point to `/sori:shows` `api-key set`; never ask for a key in chat.
3. Name the transcript you will send, so the wrong file never gets billed.

```bash
python "$SORI/train.py" "<transcript.txt>" [--out <folder>] [--theme baek|dark|dancheong] [--model <claude model>]
```

There is no `--api-key` flag: a key on the command line would land in shell
history, so `train.py` refuses one (exit 2, nothing spent). With no key
found it exits 2 with `!! no Claude API key: ...` and nothing is spent.

## Metadata and output

Transcripts written by `/sori:transcribe` or the sweep start with a
three-line header (title, `show — date`, source); `train.py` reads it. For
any other .txt pass `--title/--show/--date`. Themes: `baek` (light, the CLI
default), `dark`, `dancheong`; `train.py` does not read the app's deck-theme
setting, pass `--theme`.

Output: `<date> - <title>.pptx` and `<date> - <title>.md` next to the
transcript, or in `--out`. Report both paths; if the user wants the
takeaways, read the `.md` rather than summarizing from memory. On first
render Sori installs the deck fonts (Gowun Batang, IBM Plex, SIL OFL) into
the Windows user font folder so PowerPoint does not substitute.

## Never

- Invent a statistic, date, quote, or attribution that is not in the
  transcript, on either route.
- Run the paid route silently, in a loop, or without a per-run yes.
- Put an API key in chat, in a file, or anywhere but the environment or
  `settings.py api-key set`. Never read or print `credentials.json`.
- Retry a failed paid call without telling the user the first one may have
  been billed.
