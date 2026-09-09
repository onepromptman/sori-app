---
name: shows
description: >
  Manage Sori subscriptions and settings from the command line, no window
  needed: subscribe to a podcast RSS feed or YouTube channel, list or remove
  shows, switch Auto / Auto-train, group shows into folders, see what is new
  without transcribing, and change settings (Whisper model, caption language,
  transcript folder, deck theme, Claude API key from the environment). Use
  when the user says: subscribe to / follow / add this show, what am I
  subscribed to, remove / unfollow a show, turn auto on, put it in a folder,
  what's new on my shows, change the model / language / theme / transcript
  folder, set / clear my API key, /sori:shows. Not for transcribing one
  episode (/sori:transcribe), running the sweep (/sori:sweep), or making a
  deck (/sori:train).
---

# Sori: shows and settings

`SORI` below is the folder that holds `shows.py`: `${CLAUDE_PLUGIN_ROOT}`
when installed as a plugin, otherwise the current checkout of
https://github.com/onepromptman/sori-app. On Windows, `python` may be `py`.

Both scripts drive the same engine as the desktop app and read and write
the same `shows.json` under `%USERPROFILE%\Sori` (`SORI_HOME` overrides),
so the exe shows what the CLI did. Neither opens a window or starts a
worker.

## Setup (once)

```bash
cd "$SORI" && python -m pip install -r requirements-app.txt
```

## shows.py

| Want | Command |
|---|---|
| List shows (id, name, type, auto, auto-train, folder, last checked) | `python "$SORI/shows.py" list [--json]` |
| Subscribe | `python "$SORI/shows.py" add <url> [--auto] [--auto-train] [--folder <folder>] [--json]` |
| Unsubscribe | `python "$SORI/shows.py" remove <show>` |
| Auto-transcribe new episodes | `python "$SORI/shows.py" auto <show> on\|off` |
| Auto-train after each transcript (paid, needs a key) | `python "$SORI/shows.py" auto-train <show> on\|off` |
| Folders | `python "$SORI/shows.py" folder list \| add <name> \| rename <folder> <name> \| remove <folder> \| set <show> <folder>` |
| What is new, without transcribing (network) | `python "$SORI/shows.py" check [--json]` |

`<show>` and `<folder>` take an id or an exact name, case-insensitive; an
ambiguous name is an error, so use the id from `list`. `add` fetches the
feed, so it needs network. A "twin" warning on stderr (same show already
followed through RSS and YouTube) is advice, not a failure: tell the user
and suggest keeping one door. A fresh subscription offers exactly one
(the newest) episode.

## settings.py

| Want | Command |
|---|---|
| Show everything (key shows as set, last 4, or not set) | `python "$SORI/settings.py" show [--json]` |
| Whisper model | `python "$SORI/settings.py" model <tiny.en\|base.en\|small.en\|large-v3>` |
| Caption language | `python "$SORI/settings.py" lang <auto\|en\|ko>` |
| Deck theme | `python "$SORI/settings.py" deck-theme <baek\|dark\|dancheong>` |
| Transcript folder | `python "$SORI/settings.py" transcripts-dir <path>` or `transcripts-dir --default` |
| Claude API key | `python "$SORI/settings.py" api-key set` / `api-key status` / `api-key clear` |

`api-key set` reads the key from the `ANTHROPIC_API_KEY` environment
variable only, never from an argument, and saves it to `credentials.json`
(never `shows.json`). Flow: ask the user to export `ANTHROPIC_API_KEY` in
the shell Claude runs in, then run `api-key set`; it prints `saved (...last4)`.
Do not ask the user to paste the key into chat, do not echo it, and never
print more than its last 4 characters.

On a laptop CPU `small.en` is about five times faster than `large-v3` with
nearly the same quality on talk shows; suggest it when several shows are on
Auto.

## Exit codes

`0` ok; `1` the engine refused (message on stderr prefixed `!! `, repeat it
to the user); `2` usage error. `--json` prints the engine's data for
scripting; the human table is the default.

## Never

- Put an API key on a command line or in chat.
- Turn `auto-train` on without saying it spends money per episode.
- Read or print `credentials.json`.
