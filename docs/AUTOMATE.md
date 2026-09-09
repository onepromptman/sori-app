# Automating Sori: three ways to run the daily sweep

All three run the same engine, `app.py --sweep`: check every subscribed show,
transcribe new episodes for shows marked Auto, generate a training for shows
marked Auto-train (paid), append a block to `sweep.log`. They differ in where
the machine is, what it can transcribe, and where the files land.

| | (a) Windows scheduled task | (b) Cowork schedule (recommended) | (c) Cloud routine |
|---|---|---|---|
| How | `setup-auto-sweep.bat` registers a `schtasks` job that runs `Sori.exe --sweep` daily at 09:03 | A recurring Cowork task runs the `/sori:sweep` skill on your PC | A Claude Code `/schedule` routine runs `cloud/sweep_cloud.sh` on a cloud runner |
| Transcribes | Everything: YouTube captions and Whisper for audio/RSS | Everything (same engine, same PC) | YouTube captions only; no Whisper, RSS shows refused by `cloud/guard.py` |
| Needs | The unzipped exe; PC on at 09:03 | Cowork + the Sori plugin + Python deps; PC on when it fires | A private `sori-output` repo, a GitHub token, optionally `ANTHROPIC_API_KEY`; PC can be off |
| Output lands in | `%USERPROFILE%\Sori\Transcripts\` | `%USERPROFILE%\Sori\Transcripts\` (same folder the exe reads) | `sori-output/state/Transcripts/`, one commit per run |
| Tells you what happened | Nothing; read `sweep.log` | A message in Cowork after every run | A git commit message with the counts; details in `sweep.log` |
| Training (paid) | If a key is saved in Settings | If a key is saved in Settings | Blocked until `app.py` reads `ANTHROPIC_API_KEY` on the sweep path (see `cloud/ROUTINE.md`) |
| Status | Shipped, used since v2 | Prompt below; needs the `/sori:sweep` skill from the v3.2 skill split | Spec only, in `cloud/`; creating it is ask-first |

Pick (a) if you never open Claude. Pick (b) if you already use Cowork on
this PC: it is the same full-strength sweep with a readable report instead
of a log file. Pick (c) only for YouTube shows you want swept even when the
PC is off.

## (a) Windows scheduled task

Double-click `setup-auto-sweep.bat` in the unzipped Sori folder once. It
creates the task `Sori Daily Sweep` (`schtasks /create ... /sc daily /st
09:03`) that runs `Sori.exe --sweep` with no window. Everything lands in
`%USERPROFILE%\Sori`: `Transcripts\<Show>\<date> - <title>.txt` and, for
Auto-train shows with a saved key, `Trainings\<Show>\...pptx` + `.md`. To
check it, open the app (the Library shows the new files) or read the last
block of `%USERPROFILE%\Sori\sweep.log`; each block ends with `Done in Ns:
N transcribed, N failed, N skipped, N trained, N training failed.` Remove
it with `schtasks /delete /tn "Sori Daily Sweep" /f`. The PC has to be on
and awake at 09:03; a missed run is not caught up.

## (b) Cowork schedule (the Claude-native door)

Prerequisites, once:

1. The Sori plugin is installed in Claude Code / Cowork
   (`/plugin marketplace add onepromptman/sori-app`, `/plugin install sori@sori`)
   and `/sori:sweep` shows up in `/help`.
2. Python deps: `py -m pip install -r requirements-app.txt` in the checkout
   the plugin points at (Whisper included; the Cowork sweep is full-strength).
3. `SORI_HOME` is left **unset**, so the sweep reads and writes the same
   `%USERPROFILE%\Sori` the desktop app uses. Set it only if you deliberately
   want a second, separate subscription list.
4. Do not also leave (a) registered on the same `shows.json`: two sweeps on
   one state dir both queue the same episodes.

Create a recurring Cowork task, daily, 09:03, with this prompt verbatim:

```
Run the Sori sweep with /sori:sweep, then tell me which transcripts landed and which shows had nothing new; if a show failed, say why.
```

What lands where: the same as (a), `%USERPROFILE%\Sori\Transcripts\<Show>\`
and `Trainings\<Show>\`, so the desktop app's Library shows them the next
time it opens. How to check: the Cowork message after each run lists the
saved paths and per-show errors; `%USERPROFILE%\Sori\sweep.log` has the
same block. Training runs only for shows you marked Auto-train and only if
a key is saved (Settings, or `settings.py api-key set` with
`ANTHROPIC_API_KEY` in the environment); it costs money per new episode, so
leave Auto-train off until you want that.

## (c) Cloud routine (captions-only)

A `/schedule` routine clones the repo into a cloud runner, installs
`requirements-captions.txt` (yt-dlp, anthropic, python-pptx, numpy,
matplotlib; no Whisper), and runs `cloud/sweep_cloud.sh`. The full spec,
the verbatim routine prompt, the secrets, and the dry-run-first procedure
are in [`cloud/ROUTINE.md`](../cloud/ROUTINE.md); the output layout is in
[`cloud/README.md`](../cloud/README.md).

What lands where: a private repo, proposed as `onepromptman/sori-output`
(handoff Decision 2, recommended, not yet confirmed by Bryan). Its
`state/shows.json` is the cloud's own subscription list (YouTube channels
only), and each run commits `state/Transcripts/...`, `state/sweep.log`, and
any decks under `state/Trainings/`, with the message `sweep <UTC stamp>: N
transcribed, M trained`. How to check: the commit list on `sori-output`, or
`git pull` a local checkout and open the files. Nothing here is created
yet: the repo and the routine are both ask-first, and the paid half waits
on an `ANTHROPIC_API_KEY` fallback in `app.py` that is gated to the cloud
entrypoint (never a bare env read: the desktop scheduled sweep shares that
function, and a stray shell key must not enable paid auto-train there).
