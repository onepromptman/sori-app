---
name: transcribe
description: >
  Turn one podcast episode, YouTube video, MP3 URL, or local audio file into
  a transcript (.txt). Free and local on any OS: YouTube captions, or Whisper
  on this machine (Apple GPU on a Mac, CPU elsewhere), no API key. Use when
  the user says: transcribe this podcast / episode / YouTube video / audio
  file, get the transcript, find the episode about X and transcribe it, list
  the episodes in this feed, /sori:transcribe. Not for subscribed shows or
  settings (/sori:shows), the daily sweep across every show (/sori:sweep),
  training decks (/sori:train), or installing (/sori:setup).
---

# Sori: transcribe one thing

`SORI` below is the folder that holds `sori.py`: `${CLAUDE_PLUGIN_ROOT}`
when installed as a plugin, otherwise a checkout of
https://github.com/onepromptman/sori-app. `python3` may be `python` or `py`
on Windows.

The first command on a new machine creates Sori's own environment under
`~/Sori/.venv` (about a minute, prints what it installs). Say so before it
happens, or run `/sori:setup` first to make it a visible step. The first
Whisper run also downloads a model (~150 MB for `base.en`) into the user
cache; say that too.

## Verbs

### 1. Transcript from a YouTube video (fastest, uses captions)

```bash
python3 "$SORI/sori.py" transcribe youtube "<youtube url>" --out "<name>.txt" [--lang en]
```

Works on any public video with captions. No captions: fall back to verb 3
with the audio URL, or tell the user the video has no captions. A "Sign in
to confirm you're not a bot" or HTTP 403/429 error means YouTube changed or
the IP is a datacenter/VPN one: run `python3 "$SORI/sori.py" update` once,
retry, then say so if it persists.

### 2. Find and transcribe an episode from a podcast RSS feed

```bash
python3 "$SORI/sori.py" transcribe list "<rss url>" [--search "<words>"] [--limit 20]
python3 "$SORI/sori.py" transcribe episode "<rss url>" "<title words>" --out "<name>.txt" [--model base.en]
```

`list` first when the user names a show but not an exact episode. `episode`
downloads the MP3 and runs Whisper locally; a 30-minute episode takes a few
minutes on CPU, under a minute on an Apple Silicon Mac with MLX.

### 3. Any MP3 URL or local audio file

```bash
python3 "$SORI/sori.py" transcribe audio "<mp3 url or path>" --out "<name>.txt" [--model base.en] [--device cpu]
```

`--model`: `base.en` (default, fast, English); drop `.en` for other
languages; `small`/`medium`/`large-v3` are slower and more accurate.
`--device cuda` uses an NVIDIA GPU when one is present (Windows/Linux).

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
- Start a Whisper download or the one-time install without saying so.
- Use these verbs for a whole subscription list; that is `/sori:sweep`.
