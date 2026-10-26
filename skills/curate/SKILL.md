---
name: curate
description: >
  Run the Sori training pipeline on new transcripts: triage each one against
  the owner's curriculum (curator), write the L&D brief for the ones worth
  training (ld-architect), have it reviewed (training-critic, never the
  author), and record every stage in the ledger. Free, no API key; the
  session's agents do the thinking. Use when the user says: curate, what's
  worth a training, write the briefs, run the pipeline, what did the
  pipeline do, show the ledger, /sori:curate. Not for getting transcripts
  (/sori:sweep, /sori:transcribe), rendering the deck (/sori:design), or the
  one-shot deck without a brief (/sori:train).
---

# Sori: curate (triage → brief → critique)

`SORI` below is the folder that holds `sori.py`: `${CLAUDE_PLUGIN_ROOT}`
when installed as a plugin, otherwise a checkout of
https://github.com/onepromptman/sori-app. `python3` may be `python` or `py`
on Windows. This skill spends nothing: no API call leaves Sori; the agents
run in this session.

## 0. What is waiting

```bash
python3 "$SORI/sori.py" curate --list
```

JSON: `curriculum` (path or null), `awaiting_triage` (transcribed, no
triage), `awaiting_critique` (briefed, not yet reviewed), `trainings_root`.
No curriculum: run `python3 "$SORI/sori.py" curate --init`, tell the user to
fill `~/Sori/curriculum.md` (audience, themes, thresholds; half a page), and
stop. The curator cannot judge without it.

Each episode's artifacts live in one folder,
`<trainings_root>/<Show>/<date> - <title>/`. The transcript is at
`~/Sori/Transcripts/<Show>/<same name>.txt` (`.json` beside it has segment
timestamps).

## 1. Triage, one episode at a time

Delegate to the **curator** agent with: the transcript path, the curriculum
path, the episode folder, the episode_id and show. It writes `triage.json`
and the `triaged` (and, for skip, `skipped`) ledger rows. Expect most
episodes to be `skip` or `park`; that is the point.

## 2. Brief, for `train` only

Delegate to **ld-architect** with the same paths plus `triage.json`. It
writes `brief.md`, runs the gate (`sori.py brief-check`), fixes findings,
records `briefed`.

## 3. Critique, by a different agent

Delegate to **training-critic** (never the agent that wrote the brief; it
runs on a different model). It writes `critique.md` with `PASS` or
`REVISE` and records `critiqued`. `REVISE` goes back to ld-architect once;
a second `REVISE` stops and goes to the user with both critiques.

## 4. Report

```bash
python3 "$SORI/sori.py" ledger --days 7
```

Tell the user, in this order: how many transcripts were waiting; which were
marked train / park / skip and the one-line reason each; which briefs
passed and are ready for `/sori:design`; anything that stopped. Paths, not
summaries of content: if they want the takeaways, open the brief.

## Scheduling

A Cowork task on this computer, daily, with
`docs/AUTOMATE.md` (b)'s prompt: run `/sori:sweep`, then `/sori:curate`,
then report. Decks are not built in that run unless the owner has set
`design_backend` and asked for it; `/sori:design` is the next step.

## Never

- Let the agent that wrote a brief review it.
- Write a brief for an episode the curator marked skip or park.
- Invent a quote or a number; the gate (`brief-check`) is the floor, not the ceiling.
- Read or print `credentials.json`; nothing here needs a key.
