# Sori without the app: Mac, Linux, Windows, from Claude

This is the route for anyone who is not on Windows, or who already lives
in Claude. There is no installer. A plugin in your Claude account carries
five skills and the Python scripts; the first skill you run sets up a
private Python environment in `~/Sori/.venv` and from then on you talk to
Sori in plain language. Nothing needs admin rights, an account beyond
your Claude plan, or an API key.

## What you need

- A paid Claude plan (Pro, Max, Team or Enterprise) and one of:
  - **Claude Desktop** with the **Code** tab (Mac or Windows), or
  - **Claude Code** in a terminal (Mac, Linux, Windows), or
  - **Cowork** in Claude Desktop, with the task set to run **on this
    computer** (a cloud task cannot reach YouTube or podcast hosts; see
    [SECURITY.md](SECURITY.md)).
- A Mac, Linux box or PC with a few GB free (Whisper models are 150 MB to
  3 GB depending on the size you pick) and a home internet connection.
- `python3` of any version is enough to start. On a Mac the one behind
  the Xcode command line tools is fine; Sori fetches a current Python by
  itself through `uv` when yours is too old, or asks you to install one of
  the two.

## Install (once)

**In Claude Desktop or claude.ai:** open **Customize > Plugins**, choose
**Add > Add marketplace**, enter `onepromptman/sori-app`, then add the
**sori** plugin. It is saved to your account, so Cowork and Claude Code
pick it up on their next start.

**In Claude Code (terminal):**

```
/plugin marketplace add onepromptman/sori-app
/plugin install sori@sori
```

Then, in any session:

```
/sori:setup
```

Claude runs `sori.py doctor`, tells you what it is about to install, runs
`sori.py setup`, and shows the result. Expect about a minute and a few
hundred MB of downloads. On an Apple Silicon Mac it also installs
`mlx-whisper`, so transcription runs on the GPU.

## Use

| Say | What happens |
|---|---|
| "Transcribe this YouTube video: <url>" | `/sori:transcribe` fetches the captions, saves a `.txt`, reports the word count |
| "Find the episode about X in this feed and transcribe it: <rss url>" | lists the feed, downloads the MP3, runs Whisper locally |
| "Follow this show and auto-transcribe it: <url>" | `/sori:shows add <url> --auto` |
| "Run the sweep" / "what's new on my shows" | `/sori:sweep` transcribes every new episode of your Auto shows and reports |
| "Make a training deck from that transcript" | `/sori:train`: Claude writes the outline from the transcript, `train.py` renders a `.pptx` and a `.md` study guide. Free. |
| "Set my deck theme / model / language" | `/sori:shows` → `settings ...` |
| "What's worth a training from this week?" / "write the briefs" | `/sori:curate`: triage against your `~/Sori/curriculum.md`, brief, critique, ledger |
| "Design the deck in Claude Design" / "export for ChatSlide" | `/sori:design`: brief → deck through the backend you set once (`design-config`) |
| "Something's broken" / "YouTube stopped working" | `/sori:setup` → `doctor`, `update`, the repair table |

Everything lands in `~/Sori/`:

```
~/Sori/
  .venv/                 Sori's own Python (delete to reinstall; nothing else is in it)
  shows.json             subscriptions and settings
  credentials.json       only if you saved a Claude key; never required
  Transcripts/<Show>/<date> - <title>.txt (+ .json timings)
  Trainings/<Show>/<date> - <title>.pptx (+ .md study guide)
  sweep.log
```

## Every morning, automatically (Mac and Linux)

Pick one.

**Cowork schedule.** A recurring Cowork task, daily, running on this
computer, with the prompt from [AUTOMATE.md](AUTOMATE.md) (b). You get a
readable report after every run.

**launchd (Mac) or cron (Linux).** No Claude involved; the sweep runs
headless and logs to `~/Sori/sweep.log`. Steps and the plist are in
[AUTOMATE.md](AUTOMATE.md) (d). Remember that a sweep with an Auto-train
show and a saved key spends money per new episode; leave Auto-train off
until you want that.

Do not run both on the same `~/Sori`; two sweeps on one folder queue the
same episodes twice.

## Plain shell, no Claude

The same scripts work from any terminal:

```bash
git clone https://github.com/onepromptman/sori-app.git && cd sori-app
python3 sori.py doctor
python3 sori.py transcribe youtube "https://www.youtube.com/watch?v=..." --out ep.txt
python3 sori.py shows add "https://feeds.example.com/show.rss" --auto
python3 sori.py sweep
python3 sori.py train --brief            # the outline rules, if you want to write one yourself
```

`sori.py <verb>` is `python <script>` inside Sori's environment; the
verbs and their flags are in [CLI.md](CLI.md).

## Mac notes

- **Speed.** With MLX, `small.en` transcribes a one-hour episode in a
  couple of minutes on an M-series laptop; `large-v3` is affordable. Set it
  with `/sori:shows` → `settings model large-v3`. `SORI_WHISPER_BACKEND=faster`
  forces the CPU path if MLX misbehaves.
- **Fonts.** Decks use the `studio` theme, which names Georgia, Segoe UI
  and Consolas. Keynote and PowerPoint on a Mac substitute Helvetica Neue
  and Menlo cleanly; to name Mac faces outright, edit the three names at
  the top of `themes/studio.py` (see `themes/README.md`).
- **The window.** `python3 sori.py --profile app setup` then
  `python3 sori.py app` opens the desktop window on a Mac from source
  (pywebview over WebKit). It is not packaged or tested as a product there;
  the Claude door is the Mac product.
- **Gatekeeper.** Nothing to click through: there is no binary, only
  Python files and wheels from PyPI.

## Where it does not work

- **claude.ai chat alone** (web or mobile): skills load there but cannot
  run Python. Use Claude Desktop's Code tab, Claude Code, or Cowork.
- **Cowork or Claude Code in the cloud**: the sandbox blocks YouTube and
  podcast hosts by default and YouTube bot-blocks datacenter IPs. See
  [AUTOMATE.md](AUTOMATE.md) (c) for the owner-only cloud route.
- **A VPN or office network that blocks YouTube** behaves the same as the
  cloud: transcribe the podcast MP3 (RSS) instead of the captions.
