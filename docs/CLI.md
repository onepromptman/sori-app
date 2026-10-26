# Sori command line

The desktop app runs these same scripts underneath, so both produce
identical transcripts. Use the scripts when you want one transcript now,
want to script Sori, or aren't on Windows.

## sori.py (start here on any OS)

```bash
python3 sori.py doctor          # what is installed, what is missing, the fix
python3 sori.py setup           # Sori's own Python environment in ~/Sori/.venv (once)
python3 sori.py update          # upgrade yt-dlp: fixes most "YouTube stopped working"
python3 sori.py transcribe ...  # = transcribe.py, inside that environment
python3 sori.py shows ...       # = shows.py
python3 sori.py settings ...    # = settings.py
python3 sori.py train ...       # = train.py
python3 sori.py sweep           # = app.py --sweep
python3 sori.py selftest        # = app.py --selftest (profile-aware)
python3 sori.py app             # = app.py (the window)
```

The launcher never installs into the system Python. It uses `uv` when it is
on the PATH (and fetches a Python 3.12 by itself if yours is older), else the
running interpreter's `venv` when that interpreter is 3.11 or newer. Profiles:
`--profile claude` (default: yt-dlp, faster-whisper, python-pptx, plus
mlx-whisper on Apple Silicon), `captions` (adds anthropic; no Whisper), `app`
(the full window stack). `SORI_HOME=<dir>` moves the state and the
environment together. Any pass-through verb runs `setup` first if the
environment is missing. Everything below is what those verbs run.

The old way still works if you manage your own environment:

```bash
pip install -r requirements.txt        # transcription only (Python 3.11+)
pip install -r requirements-claude.txt # transcription + decks, no window (what sori.py installs)
pip install -r requirements-app.txt    # + training via the API and the app window
```

## transcribe.py

| Want | Command |
|---|---|
| Browse or search a podcast feed | `python transcribe.py list "<rss url>" --search "words"` |
| Find an episode and transcribe it | `python transcribe.py episode "<rss url>" "title words" --out ep.txt` |
| Transcript from a YouTube video (captions, seconds) | `python transcribe.py youtube "<video url>" --out ep.txt` |
| Any MP3 URL or local audio file (local Whisper) | `python transcribe.py audio "<url or path>" --out ep.txt` |
| Set or fix the saved header on any of the above | add `--title "<t>" --show "<s>" --date YYYY-MM-DD` |

Every podcast feed carries a direct link to each episode's audio (the
`<enclosure>` tag). Podcast apps and directories show the feed URL, or
search for `"<show name>" rss feed`.

**Models.** `--model` defaults to `base.en` (fast, English only). Drop the
`.en` for other languages. `small`, `medium`, and `large-v3` are slower and
more accurate; useful for noisy audio, accents, or technical vocabulary.
`--device cuda` uses an NVIDIA GPU when one is present. On an Apple Silicon
Mac with `mlx-whisper` installed (the launcher does it) the same model names
run on the Apple GPU; `SORI_WHISPER_BACKEND=faster|mlx` overrides the choice.

**Completeness.** Episodes often carry ad reads and segments that are cut
from the show's YouTube upload. For the whole thing, transcribe the podcast
MP3 (`audio` or `episode`) rather than the captions. Every run prints a
words-per-minute check to stderr; spoken English runs about 150 to 220 wpm,
and a much lower number means content is missing.

## train.py (transcript to deck + study guide)

Two routes into one renderer.

| Route | Command | Cost |
|---|---|---|
| Outline written by a Claude Code session (the plugin's default) | `python train.py --brief` prints the rules and JSON schema; write `outline.json`; then `python train.py "<transcript>" --outline outline.json --theme baek` | free, no key |
| Claude API call (what the exe does) | `python train.py "Transcripts/The Daily/2026-09-04 - Some Episode.txt" --theme baek` | one paid call on your key |

Both write a `.pptx` deck and a `.md` study guide next to the transcript,
or in `--out`. The outline route validates the JSON the same way the API
response is validated (6 to 20 slides, known slide kinds, verbatim quotes,
a study guide) and exits 1 with `!! ...` when it does not fit.

API route key lookup: `ANTHROPIC_API_KEY`, then the key saved by the app or
`settings.py api-key set`. There is no `--api-key` flag (a key on the
command line lands in shell history); a stray one exits 2 and spends
nothing. Themes: `studio` (the default, unbranded, no fonts to
install). A checkout that also has the private `engine/` offers `baek`
(light), `dark` and `dancheong` on top.

Transcripts saved by `transcribe.py` or the sweep begin with a three-line
header (title, `show — date`, source URL) that `train.py` reads; pass
`--title/--show/--date` for any other `.txt`.

## app.py

```bash
python app.py             # open the window
python app.py --sweep     # headless: check feeds, transcribe Auto shows, exit
python app.py --selftest  # confirm every backend is installed
```

`--sweep` is what the daily scheduled task runs. Subscriptions come from
`~/Sori/shows.json` (`%USERPROFILE%\Sori\shows.json` on Windows) (the app and `shows.py` both write it); set
`SORI_HOME` to use another folder. Output goes to stdout and is appended to
`sweep.log` in the same folder.

## shows.py

Subscriptions from the command line, through the same engine as the app,
so the window shows what the CLI did. Honours `SORI_HOME`. Opens no window,
starts no worker.

| Want | Command |
|---|---|
| List shows: id, name, type, auto, auto-train, folder, last checked | `python shows.py list [--json]` |
| Subscribe (RSS feed, YouTube channel, `@handle`, playlist) | `python shows.py add <url> [--auto] [--auto-train] [--folder <folder>] [--json]` |
| Unsubscribe | `python shows.py remove <show>` |
| Auto-transcribe new episodes | `python shows.py auto <show> on\|off` |
| Auto-train after each transcript (needs a key, costs money) | `python shows.py auto-train <show> on\|off` |
| List folders | `python shows.py folder list` |
| Add, rename, remove a folder | `python shows.py folder add <name>` / `folder rename <folder> <name>` / `folder remove <folder>` |
| Put a show in a folder | `python shows.py folder set <show> <folder>` |
| What is new on every show, without transcribing (network) | `python shows.py check [--json]` |

`<show>` and `<folder>` accept an id or an exact name, case-insensitive; an
ambiguous name is an error. `add` fetches the feed and, when the same show
is already followed through the other door (RSS and YouTube), prints a twin
warning on stderr and still adds it.

## settings.py

| Want | Command |
|---|---|
| Show model, lang, transcripts_dir, deck_theme, api key (set, last 4, or not set) | `python settings.py show [--json]` |
| Whisper model | `python settings.py model <tiny.en\|base.en\|small.en\|large-v3>` |
| Caption language | `python settings.py lang <auto\|en\|ko>` |
| Deck theme | `python settings.py deck-theme <studio\|…>` (`settings.py show` lists what this checkout offers) |
| Transcript folder | `python settings.py transcripts-dir <path>` / `transcripts-dir --default` |
| Save the Claude API key | `python settings.py api-key set` (reads `ANTHROPIC_API_KEY` from the environment only, never an argument; prints `saved (...last4)`) |
| Key status / clear | `python settings.py api-key status` / `api-key clear` |

The key goes to `credentials.json`, never `shows.json`, and is never
printed beyond its last 4 characters.

**Exit codes** for both scripts: `0` ok; `1` when the engine refuses (the
message goes to stderr prefixed `!! `); `2` usage error. `--json` prints the
engine's data instead of a table.

## Older double-click route (no Python knowledge)

`install.bat` installs Python's dependencies once (it opens the Python
download page if Python is missing; tick *Add python.exe to PATH*).
`transcribe.bat` then asks for a link, writes the transcript to your
Desktop, and opens it in Notepad. The exe replaced this route; it still
works. Kept as the no-Python route for now.
