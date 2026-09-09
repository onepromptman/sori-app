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

## One-time setup (check before the first command)

```bash
cd "$SORI"
python -m pip install -r requirements.txt        # transcription only
```

The first Whisper run downloads a ~150 MB model into the user cache; say so
before it happens.

## Verbs

### 1. Transcript from a YouTube video (fastest, uses captions)

```bash
python "$SORI/transcribe.py" youtube "<youtube url>" --out "<name>.txt" [--lang en]
```

Works on any public video with captions. No captions: fall back to verb 3
with the audio URL, or tell the user the video has no captions.

### 2. Find and transcribe an episode from a podcast RSS feed

```bash
python "$SORI/transcribe.py" list "<rss url>" [--search "<words>"] [--limit 20]
python "$SORI/transcribe.py" episode "<rss url>" "<title words>" --out "<name>.txt" [--model base.en]
```

`list` first when the user names a show but not an exact episode. `episode`
downloads the MP3 and runs Whisper locally; a 30-minute episode takes a few
minutes on CPU.

### 3. Any MP3 URL or local audio file

```bash
python "$SORI/transcribe.py" audio "<mp3 url or path>" --out "<name>.txt" [--model base.en] [--device cpu]
```

`--model`: `base.en` (default, fast, English); drop `.en` for other
languages; `small`/`medium`/`large-v3` are slower and more accurate.
`--device cuda` uses an NVIDIA GPU when one is present.

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
