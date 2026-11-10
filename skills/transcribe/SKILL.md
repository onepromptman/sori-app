---
name: transcribe
description: >
  Turn one podcast episode, YouTube video, MP3 URL, or local audio file into
  a transcript (.txt). Free and local: YouTube captions or Whisper on CPU, no
  API key. Use when the user says: transcribe this podcast / episode / YouTube
  video / audio file, get the transcript, find the episode about X and
  transcribe it, list the episodes in this feed, /sori:transcribe. Not for
  subscribed shows or settings (/sori:shows), the daily sweep across every
  show (/sori:sweep), or training decks (/sori:train).
---

# Sori: transcribe one thing

`SORI` below is the folder that holds `transcribe.py`: `${CLAUDE_PLUGIN_ROOT}`
when installed as a plugin, otherwise the current checkout of
https://github.com/onepromptman/sori-app. On Windows, `python` may be `py`.

## Get ready (every time, before the first command)

```bash
python "$SORI/preflight.py" transcribe
```

This checks Python (3.11 or newer), sets up Sori's own environment the first
time, and prints `SORI_PY=<path>` on its last line. `PY` below is that path:
run every Sori script with it. Tell the user anything it prints after `note:`
before you go on. If it ends with a line starting `!!`, repeat that line to
the user and stop. Never install packages by hand. The first
Whisper run downloads a model of about 150 MB into the user cache; the
preflight says so when that is still ahead, and so must you.

## Verbs

### 1. Transcript from a YouTube video (fastest, uses captions)

```bash
"$PY" "$SORI/transcribe.py" youtube "<youtube url>" --out "<name>.txt" [--lang en]
```

Works on any public video with captions. No captions: fall back to verb 3
with the audio URL, or tell the user the video has no captions.

### 2. Find and transcribe an episode from a podcast RSS feed

```bash
"$PY" "$SORI/transcribe.py" list "<rss url>" [--search "<words>"] [--limit 20]
"$PY" "$SORI/transcribe.py" episode "<rss url>" "<title words>" --out "<name>.txt" [--model base.en]
```

`list` first when the user names a show but not an exact episode. `episode`
downloads the MP3 and runs Whisper locally; a 30-minute episode takes a few
minutes on CPU.

### 3. Any MP3 URL or local audio file

```bash
"$PY" "$SORI/transcribe.py" audio "<mp3 url or path>" --out "<name>.txt" [--model base.en] [--device cpu]
```

`--model`: `base.en` (default, fast, English); drop `.en` for other
languages; `small`/`medium`/`large-v3` are slower and more accurate.
`--device cuda` uses an NVIDIA GPU when one is present. The saved file starts
with Sori's three-line header; the title is the file name unless you pass
`--title` (and `--show`, `--date` when the user gives them).

A command that cannot finish prints one line starting `!!` and exits 1
(feed unreachable, not a feed, file not found). Repeat it to the user.

## After a transcript lands

- Report the path and the word count (`wc -w`). Spoken English runs
  150 to 220 words per minute, so a much lower count means captions or audio
  were incomplete; say so. Podcast MP3s often carry segments cut from the
  YouTube upload, so for the whole episode prefer verb 2 or 3 over captions.
- If the user wants a summary, key points, or quotes, read the file and
  answer from it. Do not summarize from memory of the show.
- If the user wants a deck or study guide from it, hand off to `/sori:train`
  (free by default: the session writes the outline and train.py renders it; the
  paid API route is optional and asks first).

## Never

- Invent transcript content or quotes.
- Start a Whisper download without saying so.
- Use these verbs for a whole subscription list; that is `/sori:sweep`.
