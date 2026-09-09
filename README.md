# Sori

Follow podcasts and YouTube channels, turn every new episode into text on
your own machine, and, if you want, turn a transcript into a training deck
and study guide.

Transcription is free and local: no account, no API key, nothing leaves
your computer except the feed and audio fetches. Training generation from
the app is the one paid step: it calls the Claude API with your own key, and
you can ignore it entirely. From Claude Code or Cowork the session writes
the deck outline itself and Sori only renders it, so that door needs no key.

![Sori's queue: new, running, failed and stopped episodes, each with Transcribe, Stop or Retry, and a Dismiss control](docs/screenshot.png)

```mermaid
flowchart LR
    A[Podcast RSS feed] --> C{New episode}
    B[YouTube channel] --> C
    C -->|video| D[Captions, seconds]
    C -->|audio| E[Whisper on your CPU, minutes]
    D --> F[Transcript .txt + timings]
    E --> F
    F -->|optional, your Claude key| G[Training deck .pptx + study guide .md]
```

## Get it

Sori is two products over one engine: the Windows app is first-class, and a
Claude-native Sori (the plugin plus the Python CLIs, no window) ships
alongside it, with one parity rule: anything the window can do, the CLI can
do too, from the same `shows.json`.

| Route | For | Steps |
|---|---|---|
| **Windows app** | most people | download `Sori-win64.zip` from the [latest release](https://github.com/onepromptman/sori-app/releases/latest), extract, double-click `Sori.exe` |
| **Claude Code / Cowork plugin** | "transcribe this for me" in plain language | `/plugin marketplace add onepromptman/sori-app` then `/plugin install sori@sori`, then `/sori:transcribe`, `/sori:shows`, `/sori:sweep`, `/sori:train` (paid) |
| **From source** | any OS with Python 3.11+ | `pip install -r requirements-app.txt` then `python app.py` |
| **Command line** | one transcript now, or scripting | `python transcribe.py youtube "<url>" --out ep.txt`; `shows.py` and `settings.py` manage subscriptions and settings, see [docs/CLI.md](docs/CLI.md) |

**CLI-only for now:** nothing. Every window feature has a CLI twin:
`shows.py` mirrors the source list (add, remove, Auto, Auto-train,
folders) and `settings.py` mirrors Settings, so the app shows whatever the
CLI did and vice versa. Scheduling options (Windows task, Cowork, cloud
routine) are compared in [docs/AUTOMATE.md](docs/AUTOMATE.md).

Two things on the first app launch. Extract the zip before running
(right-click, **Extract All**); an exe run from inside the zip window fails
with *Failed to load Python DLL* because Windows extracts it alone. And
the blue *Windows protected your PC* box is SmartScreen, which shows for
any app without paid code-signing; click **More info, Run anyway** once.

## Use it

- **Add a source.** Paste a podcast RSS feed, a YouTube channel or
  `@handle`, or a playlist into the box on the left. The **+** menu also
  adds your own audio files and folders for grouping.
- **Queue** shows what is new. **Transcribe** one, tick several, or
  **Stop** a running job. Anything you pick by hand runs next, ahead of
  what Auto queued (Stop the running one first if you want yours now).
- **Dismiss** (the × on a row, or **Dismiss all new**) skips an episode
  for good. It will not come back on the next check or after a restart.
- **Auto** on a source transcribes its new episodes by itself while the
  app is open. **Auto-train** also generates a training after each one
  (needs a key).
- **Library** holds every transcript with search *inside* the text. The
  reader has timestamps, find, copy, `.md` and `.srt` export, and
  **Generate Training**.
- **Settings**: Whisper model, caption language, transcript folder, deck
  theme, Claude API key.

Two things that keep the queue sane. Follow a show through one door, not
both; the same show as RSS *and* YouTube gives you every episode twice, and
Sori warns when you add the second. And on a laptop CPU, `small.en` is
about five times faster than `large-v3` with nearly the same quality on
talk shows; three daily shows on Auto with `large-v3` will not drain.

The first audio transcription downloads the Whisper model, about 150 MB,
once per machine.

## Training generation

**Generate Training** on any transcript, or Auto-train on a show, sends the
transcript to Claude and gets back a deck outline plus a study guide,
grounded in the transcript only: the model is told not to invent numbers,
dates, or quotes it cannot point to. The deck renders as a real, editable
`.pptx` — fourteen slide kinds, including stat, chart and scorecard layouts
that only appear when the episode actually stated the figures.

![Fourteen slides from one podcast episode: a dark cover, agenda, bulleted
content, a pull quote, a numbered process, a colour-field section break, two
large-figure stat slides, a two-column comparison, a scorecard, and a closing
slide](docs/deck-studio.png)

Decks ship in the **`studio`** theme: an unbranded editorial look in fonts
every machine already has, so nothing is installed and a deck you send to a
colleague opens looking the way you left it. Themes are a swappable file —
change six colours, or drop in your own renderer. See
[themes/README.md](themes/README.md).

Add your key under **Settings, Training generation** (or `settings.py api-key
set`). It is stored only in your user folder, never logged, never synced. One
API call per deck; you pay Anthropic directly at their rates. `/sori:train`
skips the call: the session writes the outline against the same rules and
`train.py --outline` renders it with the same engine (see docs/CLI.md).

Everything Sori makes lives in `%USERPROFILE%\Sori\` and survives replacing
the app: `Transcripts\<Show>\`, `Trainings\<Show>\`, `shows.json`,
`credentials.json`, `sweep.log`.

## Every morning, automatically

The simplest route on Windows: double-click **`setup-auto-sweep.bat`** in
the unzipped folder. It registers a Windows task at 9:03 daily that checks
every show, transcribes new episodes for Auto shows, and trains the
Auto-train ones. Nothing appears on screen; each run appends to `sweep.log`.
Remove it with:

```
schtasks /delete /tn "Sori Daily Sweep" /f
```

Running the sweep from Cowork or a cloud routine instead, with the
trade-offs, is in [docs/AUTOMATE.md](docs/AUTOMATE.md).

Upgrading from an Earshot or Podcast Studio build? See
[docs/UPGRADING.md](docs/UPGRADING.md).

## Make it yours

Settings covers what most people change: model, language, where transcripts
go, deck theme, key, and the per-show Auto switches. The rest is one
constant each; edit, then rebuild.

| Change | Where |
|---|---|
| Voice and shape of every training | `SYSTEM_PROMPT` in `training.py`, five house rules; rewrite them and the output changes completely |
| Which Claude model writes it | `DEFAULT_MODEL` in `training.py` |
| Deck length and slide types | `SLIDE_KINDS` and the `slides` min/max in `training.py` |
| Cost ceiling per episode | `MAX_TRANSCRIPT_CHARS` in `training.py` |
| Deck look | six colours and three font names at the top of `themes/studio.py`, or a whole new backend — see [themes/README.md](themes/README.md) |
| Daily sweep time | the `/st 09:03` in `setup-auto-sweep.bat` |

Only training generation has a look to change. For transcripts alone,
`training.py` and `themes/` are never touched.

## Build the exe

```bash
pip install -r requirements-app.txt
python package.py            # PyInstaller + the files that must sit beside the exe + zip
python package.py --no-build # re-zip an existing dist/Sori
```

`package.py` exists because PyInstaller emits only `Sori.exe` and
`_internal/`; the sidecar files a downloader needs (`setup-auto-sweep.bat`,
licences, the quick-start text) are copied in afterwards, and it fails
loudly if one is missing.

## License

MIT, see [LICENSE](LICENSE). Bundled fonts (Gowun Batang, IBM Plex) are
SIL OFL 1.1 and Python dependencies keep their own licences; see
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md), which also ships in the
zip.
