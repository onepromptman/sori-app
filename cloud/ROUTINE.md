# The Sori cloud routine (captions-only)

> **Maintainer's own setup.** This page is the operator runbook, not a user
> guide. The repos it names (`onepromptman/sori`, `onepromptman/sori-output`)
> are private and will 404 for you. It is published because the shape is
> worth copying: point the two repo names at your own and the rest holds.

A Claude Code scheduled cloud agent (`/schedule`) that runs
`cloud/sweep_cloud.sh` once a day: checks the YouTube channels listed in the
output repo's `state/shows.json`, transcribes new videos from captions, and
commits the results. No Whisper, no window, no PC that has to be on.

**Status: not created.** Creating a routine is recurring and can spend
money, so it is ask-first. This page is the exact spec so the creation is a
copy-paste once Bryan says yes.

## What Bryan must confirm first

1. **Decision 2 (destination).** Outputs go to a private GitHub repo
   `onepromptman/sori-output`, one commit per run (recommended in the v3.2
   handoff; the alternative was Google Drive via connector). Creating that
   repo is itself ask-first.
2. **Spend.** The dry run below has training disabled and costs nothing
   beyond the routine's own runtime. The first run with `ANTHROPIC_API_KEY`
   set and an auto-train show is a paid Claude call per new video and needs
   an explicit yes. Also see the blocker under "Before the paid run".
3. **Repo access for the routine.** `onepromptman/sori` is private; the
   routine needs read access to it and write (push) access to `sori-output`.

## Prerequisites (one-time, by Bryan)

- `onepromptman/sori-output` exists, private, with the layout in
  `cloud/README.md`: a `.gitignore` holding `state/credentials.json`,
  `state/*.json.tmp`, `state/*.json.bad`, and a `state/shows.json` that
  lists only YouTube shows. Build that file from a Sori checkout:

  ```bash
  SORI_HOME=/path/to/sori-output/state py shows.py add "https://www.youtube.com/@lexfridman" --auto
  SORI_HOME=/path/to/sori-output/state py shows.py list
  ```

  Add `--auto-train` only after the paid run is approved.
- Secrets on the routine:
  - a GitHub token that can read `onepromptman/sori` and push to
    `onepromptman/sori-output` (fine-grained PAT scoped to those two repos,
    Contents: read on sori, read/write on sori-output);
  - `ANTHROPIC_API_KEY`, **optional**; leave it unset for the dry run.

## Schedule

Daily at 09:03 America/Los_Angeles to match `setup-auto-sweep.bat`. Cron
is UTC: `3 16 * * *` during PDT (UTC-7), `3 17 * * *` during PST (UTC-8).
Pick one and accept the hour drift, or use the scheduler's timezone field
if it has one. The desktop-side Windows task and this routine must not
share a `shows.json`, and they do not: the cloud list lives in
`sori-output`, the desktop list in `%USERPROFILE%\Sori`.

## The routine prompt (verbatim)

```
You are running the Sori captions-only sweep. Do exactly this and nothing else.

1. Clone https://github.com/onepromptman/sori (private, use the GitHub token
   provided as a secret) at the default branch into ./sori, and clone
   https://github.com/onepromptman/sori-output into ./sori-output.
2. In ./sori run: python3 -m pip install -r requirements-captions.txt
3. Configure git in ./sori-output with user.name "sori-routine" and
   user.email "sori-routine@users.noreply.github.com".
4. From ./sori run:
     SORI_OUTPUT_DIR="$PWD/../sori-output" PY=python3 bash cloud/sweep_cloud.sh
   If ANTHROPIC_API_KEY is present in the environment leave it there; never
   print it, never write it to a file, never pass it as an argument.
5. Report, in this order: the "summary:" line the script printed; each
   "saved:" path; each "failed:" or "training failed:" line with its reason;
   each "! <show>:" feed error; whether the push happened. If the script
   exited 3, say which show the guard refused and stop. If it exited non-zero
   for any other reason, paste the last 30 lines of ./sori-output/state/sweep.log.
Do not add shows, edit shows.json, change settings, or run anything else.
```

Do **not** put `python3 app.py --selftest` in the routine as a health check:
it reports `faster_whisper` and `webview` as missing under this profile and
exits 1 by design. `cloud/guard.py` plus the sweep's own exit code are the
health check.

## Procedure: dry run first, training disabled

1. Bryan confirms items 1 to 3 above and creates `sori-output`.
2. Create the routine with the prompt above, the GitHub token as its only
   secret (no `ANTHROPIC_API_KEY`), and `state/shows.json` holding one
   YouTube channel with `auto: true`, `auto_train: false`.
3. Trigger it once by hand (or wait for the schedule). Definition of done
   for the dry run: one commit on `sori-output` whose message reads
   `sweep <stamp>: 1 transcribed, 0 trained` and whose diff adds one
   `state/Transcripts/<Show>/<date> - <title>.txt` (+ `.json`) and a new
   `sweep.log` block. A second trigger should commit `0 transcribed`
   (only `last_checked` and the log move).
4. Check it from a local checkout of `sori-output`: `git pull && tail -n 20
   state/sweep.log` and open the transcript; word count should be roughly
   150 to 220 per minute of video.

## Before the paid run

- **Blocker (cross-lane, `app.py`):** the sweep's auto-train path resolves
  the key through `app.anthropic_api_key()`, which reads `credentials.json`
  only. Until it falls back to `ANTHROPIC_API_KEY`, a cloud run with an
  auto-train show fails with "No Claude API key set" rather than spending.
  That is a safe failure, but the paid run cannot succeed before the
  fallback lands. Do not work around it by writing `credentials.json` into
  the runner: the whole point is that the key never touches the output repo.
  Any fallback must be gated to the cloud entrypoint (an explicit opt-in that
  only `sweep_cloud.sh` sets) rather than a bare `os.environ` read in
  `app.anthropic_api_key()`: that function also serves the desktop app's
  scheduled `--sweep` over Bryan's real shows, and a bare read would let a
  stray shell `ANTHROPIC_API_KEY` turn on paid auto-train without a key ever
  being entered in Settings. Which design lands is Bryan's call (spend).
- **Unverified on Linux:** deck rendering has been run only on Windows
  (`deck_render.install_fonts` writes to the Windows user font folder).
  Expect the first paid run to be a fact-finding run; budget one call.
- Then: add `ANTHROPIC_API_KEY` as a routine secret, flip one show to
  `auto_train: true` in `state/shows.json`, get Bryan's yes for that single
  run, trigger once, and confirm `1 trained` in the commit message plus a
  `.pptx` and `.md` under `state/Trainings/<Show>/`.
