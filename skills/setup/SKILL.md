---
name: setup
description: >
  First-run and repair for Sori on this machine, any OS (macOS, Linux,
  Windows): check what is installed, create Sori's own Python environment,
  install its dependencies, fix "YouTube stopped working", and add the first
  show. Use when the user says: set up Sori, install Sori, get Sori working
  on my Mac, sori doctor, something is broken, yt-dlp error, no module
  named, /sori:setup. Not for transcribing (/sori:transcribe), subscriptions
  once things work (/sori:shows), the sweep (/sori:sweep), or decks
  (/sori:train).
---

# Sori: set up or repair this machine

`SORI` below is the folder that holds `sori.py`: `${CLAUDE_PLUGIN_ROOT}`
when installed as a plugin, otherwise a checkout of
https://github.com/onepromptman/sori-app. `python3` may be `python` or `py`
on Windows; use whichever exists.

Nothing in Sori needs admin rights, an account, or an API key. Everything
it installs lands in its own virtual environment at `~/Sori/.venv`
(`%USERPROFILE%\Sori\.venv` on Windows; `SORI_HOME` moves the whole folder),
never in the system Python.

## 1. Diagnose

```bash
python3 "$SORI/sori.py" doctor
```

Read the report, not the exit code alone. It names the OS, the host Python,
whether `uv` is present, where Sori's state and environment live, which
modules import, and under `fix:` the exact command to run next. `--json`
gives the same as data.

## 2. Install (one time per machine, about a minute)

```bash
python3 "$SORI/sori.py" setup
```

What it does, in order: creates `~/Sori/.venv` (with `uv` when installed,
else the host Python's `venv` if that Python is 3.11+), installs
`requirements-claude.txt` (yt-dlp, faster-whisper, python-pptx), and on an
Apple Silicon Mac also `requirements-mac.txt` (mlx-whisper, GPU-speed
transcription). It prints every command it runs. Say what it is about to do
before running it; it downloads a few hundred MB of wheels.

If `doctor` says the host Python is too old and `uv` is missing, do NOT
pipe a download into a shell on the user's behalf. Tell them the two
choices and let them pick:

- `uv`: https://docs.astral.sh/uv/getting-started/installation/ (one
  command on their page; `brew install uv` on a Mac with Homebrew)
- Python 3.12 from https://www.python.org/downloads/

Then rerun `setup`.

Any later verb (`transcribe`, `shows`, `sweep`, `train`) runs `setup` by
itself if the environment is missing, so step 2 is only needed when you
want the install to be a visible step.

## 3. First show, first transcript

```bash
python3 "$SORI/sori.py" shows add "<rss feed or youtube channel url>" --auto
python3 "$SORI/sori.py" shows list
python3 "$SORI/sori.py" sweep
```

A fresh subscription offers exactly one episode (the newest), so the first
sweep makes one transcript. Hand off to `/sori:shows` for more.

## Repair table

| Symptom | Do |
|---|---|
| `No module named yt_dlp` / `faster_whisper` / `pptx` | `python3 "$SORI/sori.py" setup --force` |
| YouTube: "Sign in to confirm you're not a bot", "Unable to extract", HTTP 403/429 | `python3 "$SORI/sori.py" update` (upgrades yt-dlp; YouTube changes weekly). Still failing: the machine is on a datacenter or VPN IP, which YouTube blocks; use a home connection or transcribe the podcast MP3 instead |
| Whisper slow on a Mac | `doctor` should show `mlx_whisper`; if not, `setup --force`. `SORI_WHISPER_BACKEND=faster` forces the CPU path if MLX misbehaves |
| `externally-managed-environment` from pip | You bypassed the launcher. Use `sori.py`, which never installs into the system Python |
| The environment is in a bad state | Delete `~/Sori/.venv` (only that folder; transcripts live beside it) and run `setup` |

## Never

- Install into the system or Homebrew Python, or with `sudo`.
- Pipe `curl ... | sh` on the user's behalf; show the command and let them run it.
- Touch anything in `~/Sori` other than `.venv` without being asked.
- Read or print `credentials.json`.
