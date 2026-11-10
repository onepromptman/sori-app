---
name: sweep
description: >
  Run the Sori sweep: check every subscribed show, transcribe the new
  episodes of shows marked Auto, train the Auto-train ones, and report what
  landed. Headless, exits when done. Use when the user says: run the sweep,
  run Sori, do the daily run, transcribe everything new, catch up my shows,
  what did the sweep do, read sweep.log, /sori:sweep. Not for one episode
  (/sori:transcribe), changing subscriptions or settings (/sori:shows), or a
  deck from a transcript you already have (/sori:train).
---

# Sori: the sweep

`SORI` below is the folder that holds `app.py`: `${CLAUDE_PLUGIN_ROOT}`
when installed as a plugin, otherwise the current checkout of
https://github.com/onepromptman/sori-app. On Windows, `python` may be `py`.

## Get ready (every time, before the first command)

```bash
python "$SORI/preflight.py" sweep
```

This checks Python (3.11 or newer), sets up Sori's own environment the first
time, and prints `SORI_PY=<path>` on its last line. `PY` below is that path:
run every Sori script with it. Tell the user anything it prints after `note:`
before you go on. If it ends with a line starting `!!`, repeat that line to
the user and stop. Never install packages by hand.

## Run it

```bash
"$PY" "$SORI/app.py" --sweep
```

State lives in `%USERPROFILE%\Sori`; `SORI_HOME=<dir>`
points at another folder, which is how tests and staging runs stay off the
user's real subscriptions. The sweep reads `shows.json`, writes transcripts
to `Transcripts\<Show>\` and decks to `Trainings\<Show>\`, prints to stdout
and appends the same lines to `sweep.log`.

Before the first sweep on a machine, run `"$PY" "$SORI/shows.py" list`
and look at the auto-train column: a show with auto-train on and a saved
key makes one paid Claude call per new episode. Say so before running if
any show is auto-train. A sweep with no auto-train shows is free.

Whisper on CPU takes minutes per episode and the first run downloads a
model of about 150 MB; run the sweep in the background for long queues.

Only one Sori engine runs on a state folder at a time. If the app or another
sweep is already running there, this sweep prints a line ending `This sweep
did nothing.` and exits 0. Say so and stop; do not retry in a loop.

## Read the output (same shape in stdout and sweep.log)

```
=== Sori sweep - 2026-09-05 09:03:01 ===
Checked 3 show(s): 2 new episode(s).
  ! <Show>: <feed error>                          (only when a fetch failed)
  - [auto] The Daily: 2026-09-05 Some title
  - [manual] Lex Fridman: 2026-09-04 #502 ...
1 episode(s) left for manual review (show not set to auto).
  > transcribing: Some title
    downloading the Whisper model (first run only)…
    saved: ...\Transcripts\The Daily\2026-09-05 - Some title.txt
    failed: <reason> (will try again next sweep, 2 left)   |  (giving up - use Retry in the app)
  > generating training: Some title
    saved: ...\Trainings\The Daily\2026-09-05 - Some title.pptx
    training failed: <reason>
Done in 135.2s - 1 transcribed, 0 failed, 1 skipped, 0 trained, 0 training failed.
```

`No shows subscribed yet.` means `shows.json` is empty for this
`SORI_HOME`; point the user to `/sori:shows`. When asked what an earlier
sweep did, read the last `=== Sori sweep` block of `sweep.log` rather than
re-running.

## Report what landed

1. The `Done in` line, in plain words: transcribed / failed / skipped /
   trained.
2. Every `saved:` path, grouped by show. For a transcript, add the word
   count (`wc -w`); spoken English runs 150 to 220 words per minute, so a
   much lower count means captions or audio were incomplete; say so.
3. Every `failed:` and `! ` line with its reason, and whether it will retry
   or has given up.
4. `[manual]` rows: new episodes the user can transcribe by hand
   (`/sori:transcribe`) or switch to Auto (`/sori:shows`).

Feed, transcription, or training failures make the exit code nonzero. Read
the individual lines to report which item failed and whether it will retry.

## Never

- Point a sweep at the user's real state dir "just to test"; use `SORI_HOME`.
- Invent what a transcript says; open the saved file.
- Run a sweep that will train without telling the user it spends money.
