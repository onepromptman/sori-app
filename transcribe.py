#!/usr/bin/env python3
"""
podcast-transcriber — free, local, no-API-key podcast transcription.

Two paths to a transcript:
  1. YouTube captions — instant, if the episode is also posted on YouTube.
  2. Local Whisper    — works for any MP3, runs entirely on your machine.

No OpenAI/AssemblyAI key required. See README.md for setup and examples.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import re
import sys
import tempfile
import threading
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

ITUNES_NS = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd"}


class TranscriptionCancelled(Exception):
    """Raised inside a transcription when its cancel event is set."""


# ---------------------------------------------------------------------------
# RSS feed helpers
# ---------------------------------------------------------------------------

def fetch_xml(url: str, timeout: int = 30) -> bytes:
    """GET a feed URL and return raw bytes. Shared by the CLI and the app."""
    req = urllib.request.Request(url, headers={"User-Agent": "podcast-transcriber/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def parse_rss_episodes(root: ET.Element) -> list[dict]:
    """Pull episodes out of an already-parsed RSS document."""
    episodes = []
    for item in root.iterfind(".//item"):
        title_el = item.find("title")
        enclosure_el = item.find("enclosure")
        pubdate_el = item.find("pubDate")
        duration_el = item.find("itunes:duration", ITUNES_NS)
        guid_el = item.find("guid")
        if enclosure_el is None:
            continue
        url = enclosure_el.get("url", "")
        guid = (guid_el.text or "").strip() if guid_el is not None and guid_el.text else url
        episodes.append({
            "title": (title_el.text or "").strip() if title_el is not None else "",
            "mp3_url": url,
            "pub_date": (pubdate_el.text or "").strip() if pubdate_el is not None else "",
            "duration": duration_el.text if duration_el is not None else None,
            "guid": guid,
        })
    return episodes


def _parse_feed(feed_url: str) -> list[dict]:
    return parse_rss_episodes(ET.fromstring(fetch_xml(feed_url)))


def _parse_feed_with_title(feed_url: str) -> tuple[str, list[dict]]:
    """Like _parse_feed, plus the show's name from <channel><title>."""
    root = ET.fromstring(fetch_xml(feed_url))
    title_el = root.find("./channel/title")
    show = (title_el.text or "").strip() if title_el is not None and title_el.text else ""
    return show, parse_rss_episodes(root)


def _iso_date(raw: str) -> str:
    """RFC-2822 feed date (or yt-dlp's YYYYMMDD) -> YYYY-MM-DD, else ''."""
    raw = (raw or "").strip()
    if re.fullmatch(r"\d{8}", raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def cmd_list(args: argparse.Namespace) -> None:
    episodes = _parse_feed(args.feed_url)
    if args.search:
        needle = args.search.lower()
        episodes = [e for e in episodes if needle in e["title"].lower()]
    episodes = episodes[: args.limit]
    if not episodes:
        print("No matching episodes found.")
        return
    for e in episodes:
        dur = f" ({e['duration']})" if e["duration"] else ""
        print(f"- {e['title']}{dur}")
        print(f"    {e['pub_date']}")
        print(f"    {e['mp3_url']}")
        print()


# ---------------------------------------------------------------------------
# YouTube captions path
# ---------------------------------------------------------------------------

def _clean_vtt(vtt_text: str) -> str:
    """Strip VTT timing/tags and collapse rolling (repeated) caption lines."""
    out: list[str] = []
    prev = None
    for line in vtt_text.splitlines():
        if "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:")) or not line.strip():
            continue
        text = re.sub(r"<[^>]+>", "", line).strip()
        if not text or text == prev:
            continue
        if prev and (text in prev or prev in text):
            prev = text if len(text) > len(prev) else prev
            continue
        out.append(text)
        prev = text
    return re.sub(r"\s+", " ", " ".join(out)).strip()


_VTT_CUE_RE = re.compile(r"(?P<start>[\d:.,]+)\s*-->\s*(?P<end>[\d:.,]+)")


def _vtt_timestamp_to_seconds(ts: str) -> float:
    """Parse a VTT timestamp (HH:MM:SS.mmm or MM:SS.mmm) into seconds."""
    parts = ts.strip().replace(",", ".").split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", parts[0], parts[1]
    else:
        raise ValueError(f"unrecognised VTT timestamp: {ts!r}")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _vtt_segments(vtt_text: str) -> list[dict]:
    """Parse VTT cues into [{"start", "end", "text"}] (seconds, stripped text).

    Same rolling-caption dedupe as `_clean_vtt` — line by line, skip an exact
    repeat or a containment either way (keeping the longer variant) — but
    timestamped instead of flattened into one string. A survivor gets a new
    segment; a "kept the longer one" match widens the previous segment's text
    and end time instead of adding a near-duplicate.
    """
    segments: list[dict] = []
    prev = None
    cue_start = cue_end = None
    for line in vtt_text.splitlines():
        m = _VTT_CUE_RE.search(line)
        if "-->" in line and m:
            try:
                cue_start = _vtt_timestamp_to_seconds(m.group("start"))
                cue_end = _vtt_timestamp_to_seconds(m.group("end"))
            except ValueError:
                # A malformed cue isn't worth failing the whole transcript over
                # (and isn't a network error) — treat it as no current cue and
                # keep going; text under it gets skipped below like a preamble.
                cue_start = cue_end = None
            continue
        if line.startswith(("WEBVTT", "Kind:", "Language:")) or not line.strip():
            continue
        text = re.sub(r"<[^>]+>", "", line).strip()
        if not text or text == prev:
            continue
        if prev and (text in prev or prev in text):
            if len(text) > len(prev):
                segments[-1]["text"] = text
                if cue_end is not None:
                    segments[-1]["end"] = cue_end
                prev = text
            continue
        if cue_start is None:
            # Text before the first cue (or after a malformed one) has no
            # timestamp home — drop it rather than emit start=None.
            continue
        segments.append({"start": cue_start, "end": cue_end, "text": text})
        prev = text
    return segments


def pick_caption_track(available: list[str], lang: str = "en") -> str | None:
    """Choose ONE caption track from what a video offers.

    Asking yt-dlp for `en.*` looks convenient but matches every machine-
    translated variant a popular video carries (en-ar, en-de, en-es...). It
    then downloads all of them, which is both wrong (translations, not the
    original audio) and a fast route to an HTTP 429. So: pick exactly one,
    preferring the original track, and download only that.
    """
    tracks = set(available)
    if lang in tracks:
        return lang
    if f"{lang}-orig" in tracks:
        return f"{lang}-orig"
    # Real regional variants use an uppercase region (en-US, en-GB); the
    # lowercase-suffixed ones are translation pairs, which we don't want.
    regional = sorted(t for t in tracks
                      if re.fullmatch(rf"{re.escape(lang)}-[A-Z]{{2}}", t))
    return regional[0] if regional else None


def _fetch_vtt(url: str, lang: str = "en", meta: dict | None = None) -> str | None:
    """Download raw VTT caption text for a YouTube video, or None if it has none.

    Shared by `fetch_youtube_captions` and `fetch_youtube_caption_segments` so
    both go through the same track-picking and yt-dlp options.
    """
    import yt_dlp

    base_opts = {"skip_download": True, "quiet": True, "no_warnings": True}

    with yt_dlp.YoutubeDL(base_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    if meta is not None:
        # What the saved transcript's header needs; the app's sweep gets the
        # same fields from the channel feed instead.
        meta.update(title=info.get("title") or "",
                    show=info.get("channel") or info.get("uploader") or "",
                    date=_iso_date(info.get("upload_date") or ""),
                    url=info.get("webpage_url") or url)

    offered = list((info.get("subtitles") or {}).keys())
    offered += list((info.get("automatic_captions") or {}).keys())
    track = pick_caption_track(offered, lang)
    if track is None:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        ydl_opts = {
            **base_opts,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [track],
            "subtitlesformat": "vtt",
            "outtmpl": str(Path(tmp) / "%(id)s"),
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        vtt_files = sorted(Path(tmp).glob("*.vtt"))
        if not vtt_files:
            return None
        return vtt_files[0].read_text(encoding="utf-8", errors="replace")


def fetch_youtube_captions(url: str, lang: str = "en", meta: dict | None = None) -> str | None:
    """Return a cleaned caption transcript for a YouTube video, or None if it has none.

    Importable (app.py uses it); raises ImportError if yt-dlp is missing and
    never calls sys.exit, so callers can decide how to report failure.
    """
    vtt_text = _fetch_vtt(url, lang, meta)
    if vtt_text is None:
        return None
    return _clean_vtt(vtt_text)


def fetch_youtube_caption_segments(url: str, lang: str = "en") -> list[dict] | None:
    """Timestamped sibling of `fetch_youtube_captions`: [{"start","end","text"}] or None."""
    vtt_text = _fetch_vtt(url, lang)
    if vtt_text is None:
        return None
    return _vtt_segments(vtt_text)


def cmd_youtube(args: argparse.Namespace) -> None:
    meta: dict = {}
    try:
        transcript = fetch_youtube_captions(args.url, args.lang, meta)
    except ImportError:
        sys.exit("yt-dlp is required for this command: pip install yt-dlp")

    if transcript is None:
        sys.exit(
            "No captions found for this video. It may not have captions yet, "
            "or try a different --lang (e.g. --lang fr)."
        )

    _write_output(transcript, args.out, _meta_from_args(args, meta))
    _report_completeness(transcript, expected_seconds=None)


# ---------------------------------------------------------------------------
# Local Whisper path
# ---------------------------------------------------------------------------

def _download_audio(url_or_path: str, dest_dir: Path, on_progress=None, cancel=None) -> Path:
    """Download an audio URL (streamed, so long episodes never sit in RAM).

    `on_progress(fraction_or_None)` is called as bytes land; the fraction is
    None when the server sends no Content-Length. `cancel`, if given, is
    checked between chunks and raises `TranscriptionCancelled`.
    """
    if re.match(r"^https?://", url_or_path):
        dest = dest_dir / "episode.mp3"
        req = urllib.request.Request(url_or_path, headers={"User-Agent": "podcast-transcriber/1.0"})
        with urllib.request.urlopen(req) as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            got = 0
            while chunk := resp.read(262144):
                if cancel is not None and cancel.is_set():
                    raise TranscriptionCancelled()
                f.write(chunk)
                got += len(chunk)
                if on_progress:
                    on_progress(got / total if total else None)
        return dest
    return Path(url_or_path)


# Two local Whisper backends, one contract. faster-whisper (CTranslate2) is
# the default everywhere and the only one on Windows/Linux/Intel Macs. On
# Apple Silicon, mlx-whisper runs the same models on the GPU through Apple's
# MLX and is several times faster than int8 CPU decoding; sori.py installs it
# there (requirements-mac.txt) and this module picks it up when it imports.
# SORI_WHISPER_BACKEND=faster|mlx overrides the guess (tests, or a Mac where
# MLX misbehaves). Both paths yield [{"start","end","text"}] + duration.
_BACKENDS = ("faster", "mlx")

# Sori's model names are faster-whisper's. mlx-community publishes the same
# sizes under its own repo names; anything not listed follows the pattern.
MLX_REPOS = {
    "tiny.en": "mlx-community/whisper-tiny.en-mlx",
    "base.en": "mlx-community/whisper-base.en-mlx",
    "small.en": "mlx-community/whisper-small.en-mlx",
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


def mlx_repo(model_name: str) -> str:
    if "/" in model_name:          # already a repo id or a local path
        return model_name
    return MLX_REPOS.get(model_name, f"mlx-community/whisper-{model_name}-mlx")


def whisper_backend(device: str = "cpu") -> str:
    """Which local backend a transcription will use.

    `cuda` always means faster-whisper (MLX has no CUDA). Otherwise the env
    override wins, then MLX on an Apple Silicon Mac that has mlx_whisper
    installed, else faster-whisper. Importing nothing here keeps the check
    cheap enough for the app's hourly poller.
    """
    if device == "cuda":
        return "faster"
    forced = (os.environ.get("SORI_WHISPER_BACKEND") or "").strip().lower()
    if forced in _BACKENDS:
        return forced
    if (sys.platform == "darwin" and platform.machine() == "arm64"
            and importlib.util.find_spec("mlx_whisper") is not None):
        return "mlx"
    return "faster"


# Loading a WhisperModel costs seconds (weights off disk into RAM) and the app
# transcribes many episodes per process, so keep one instance per
# (model, device) alive. The Worker runs jobs serially, so a shared model is
# never asked to decode two files at once.
_MODEL_CACHE: dict[tuple[str, str], object] = {}
_MODEL_LOCK = threading.RLock()


def _hf_cache_roots() -> list[Path]:
    """The directory huggingface_hub will actually read, in its own precedence.

    Only the winning location counts: if HF_HUB_CACHE points somewhere empty,
    a copy sitting in the default cache is not going to be used, so reporting
    "already downloaded" off it would be a lie.
    """
    for var in ("HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        value = os.environ.get(var)
        if value:
            return [Path(value)]
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return [Path(hf_home) / "hub"]
    return [Path.home() / ".cache" / "huggingface" / "hub"]


def whisper_model_is_cached(model_name: str, device: str = "cpu") -> bool:
    """True if loading this model will NOT hit the network.

    A heuristic on the huggingface cache layout, used only to decide whether
    to tell the user "downloading model" before a first run. Being wrong is
    cosmetic in both directions, never a failure.
    """
    with _MODEL_LOCK:
        if (model_name, device) in _MODEL_CACHE:
            return True
    try:
        if Path(model_name).is_dir():  # an explicit local model directory
            return True
    except OSError:
        pass
    # "base.en" -> models--Systran--faster-whisper-base.en (and the distil-*
    # repos, which slot the size in the same trailing position).
    patterns = [
        f"models--*whisper-{model_name}",
        f"models--{model_name.replace('/', '--')}",
        f"models--{mlx_repo(model_name).replace('/', '--')}",
    ]
    for root in _hf_cache_roots():
        for pattern in patterns:
            try:
                if any(p.is_dir() for p in root.glob(pattern)):
                    return True
            except OSError:
                continue
    return False


def load_whisper_model(model_name: str, device: str):
    """Get (and memoize) a WhisperModel. Raises ImportError if faster-whisper is missing.

    Call this before transcribing when you want the first-run weight download
    to happen inside a step the user can see.
    """
    key = (model_name, device)
    with _MODEL_LOCK:
        model = _MODEL_CACHE.get(key)
        if model is None:
            if whisper_backend(device) == "mlx":
                from mlx_whisper.load_models import load_model

                # Pulls the weights from the Hugging Face hub on first use (the
                # visible "downloading model" step), then they are on disk.
                model = load_model(mlx_repo(model_name))
                _MODEL_CACHE[key] = model
                return model
            from faster_whisper import WhisperModel

            compute_type = "int8" if device == "cpu" else "float16"
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            _MODEL_CACHE[key] = model
        return model


def _transcribe_whisper_segments(
    audio_path: Path, model_name: str, device: str, on_progress=None, cancel=None, language=None
) -> tuple[list[dict], float]:
    """Transcribe locally with faster-whisper, keeping per-segment timing.

    Raises ImportError if faster-whisper isn't installed. `on_progress(fraction)`
    is called per decoded segment (fraction of audio done); `cancel`, if given,
    is checked between segments and raises `TranscriptionCancelled`. `language`
    is passed through to faster-whisper only when set (None lets it auto-detect
    or defers to an English-only model).
    """
    if whisper_backend(device) == "mlx":
        return _transcribe_mlx_segments(audio_path, model_name, on_progress=on_progress,
                                        cancel=cancel, language=language)
    model = load_whisper_model(model_name, device)
    # beam_size=5 + vad_filter is a solid default: accurate without being slow
    # on CPU, and voice-activity filtering skips music/silence beds cleanly.
    kwargs = {"beam_size": 5, "vad_filter": True}
    if language is not None:
        kwargs["language"] = language
    segments, info = model.transcribe(str(audio_path), **kwargs)
    out: list[dict] = []
    for seg in segments:
        if cancel is not None and cancel.is_set():
            raise TranscriptionCancelled()
        out.append({"start": round(seg.start, 2), "end": round(seg.end, 2), "text": seg.text.strip()})
        if on_progress and info.duration:
            on_progress(min(seg.end / info.duration, 1.0))
    return out, info.duration


def _transcribe_mlx_segments(
    audio_path: Path, model_name: str, on_progress=None, cancel=None, language=None
) -> tuple[list[dict], float]:
    """mlx-whisper twin of the faster-whisper path, same return shape.

    mlx_whisper.transcribe() decodes the whole file and returns one dict, so
    progress is reported per segment after the fact and cancel is honoured
    between segments while the result is read out, not mid-decode. Duration
    comes from the last segment's end (MLX does not report the file length).
    """
    import mlx_whisper

    load_whisper_model(model_name, "cpu")   # make the download a visible step
    kwargs = {"path_or_hf_repo": mlx_repo(model_name), "verbose": None}
    if language is not None:
        kwargs["language"] = language
    result = mlx_whisper.transcribe(str(audio_path), **kwargs)
    raw = result.get("segments") or []
    duration = float(raw[-1].get("end") or 0.0) if raw else 0.0
    out: list[dict] = []
    for seg in raw:
        if cancel is not None and cancel.is_set():
            raise TranscriptionCancelled()
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        out.append({"start": round(float(seg.get("start") or 0.0), 2),
                    "end": round(float(seg.get("end") or 0.0), 2), "text": text})
        if on_progress and duration:
            on_progress(min(out[-1]["end"] / duration, 1.0))
    return out, duration


def _transcribe_whisper(
    audio_path: Path, model_name: str, device: str, on_progress=None
) -> tuple[str, float]:
    """Thin wrapper over `_transcribe_whisper_segments` for CLI/back-compat."""
    segments, duration = _transcribe_whisper_segments(audio_path, model_name, device, on_progress=on_progress)
    return " ".join(s["text"] for s in segments), duration


def _whisper_or_exit(audio_path: Path, model_name: str, device: str) -> tuple[str, float]:
    try:
        return _transcribe_whisper(audio_path, model_name, device)
    except ImportError:
        sys.exit("a local Whisper backend is required for this command: "
                 "pip install faster-whisper (or mlx-whisper on Apple Silicon), "
                 "or run `python3 sori.py setup`")


def cmd_audio(args: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = _download_audio(args.url_or_path, Path(tmp))
        transcript, duration = _whisper_or_exit(audio_path, args.model, args.device)
    _write_output(transcript, args.out, _meta_from_args(args, {"url": args.url_or_path}))
    _report_completeness(transcript, expected_seconds=duration)


def cmd_episode(args: argparse.Namespace) -> None:
    show, episodes = _parse_feed_with_title(args.feed_url)
    needle = args.search.lower()
    matches = [e for e in episodes if needle in e["title"].lower()]
    if not matches:
        sys.exit(f'No episode titled like "{args.search}" found in this feed. Try `list` first.')
    episode = matches[0]
    print(f"Found: {episode['title']}")
    print(f"  {episode['mp3_url']}\n")

    with tempfile.TemporaryDirectory() as tmp:
        audio_path = _download_audio(episode["mp3_url"], Path(tmp))
        transcript, duration = _whisper_or_exit(audio_path, args.model, args.device)

    out = args.out or _slugify(episode["title"]) + ".txt"
    meta = {"title": episode["title"], "show": show, "date": _iso_date(episode["pub_date"]),
            "url": episode["mp3_url"]}
    _write_output(transcript, out, _meta_from_args(args, meta))
    _report_completeness(transcript, expected_seconds=duration)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", "-", text)[:80]


def header_block(meta: dict | None) -> str:
    """The three-line header Sori's sweep writes (title / "show — date" / url),
    so a CLI transcript carries its own metadata and train.py reads it back
    without --title/--show/--date. Empty when there is no title to lead with."""
    if not meta or not (meta.get("title") or "").strip():
        return ""
    return (f"{meta.get('title', '').strip()}\n"
            f"{(meta.get('show') or '').strip()} — {(meta.get('date') or '').strip()}\n"
            f"{(meta.get('url') or '').strip()}\n\n")


def _meta_from_args(args: argparse.Namespace, base: dict | None) -> dict:
    """--title/--show/--date override whatever the source reported."""
    meta = dict(base or {})
    for key in ("title", "show", "date"):
        value = getattr(args, key, None)
        if value:
            meta[key] = value
    return meta


def _write_output(transcript: str, out_path: str | None, meta: dict | None = None) -> None:
    if out_path:
        Path(out_path).write_text(header_block(meta) + transcript, encoding="utf-8")
        print(f"Saved to {out_path}")
    else:
        print(transcript)  # stdout stays raw text for piping


def _report_completeness(transcript: str, expected_seconds: float | None) -> None:
    words = len(transcript.split())
    if expected_seconds:
        minutes = expected_seconds / 60
        wpm = words / minutes if minutes else 0
        print(
            f"\n[{words} words over {minutes:.1f} min of audio — {wpm:.0f} wpm. "
            f"Spoken English typically runs ~150-220 wpm; a much lower number "
            f"usually means part of the transcript is missing.]",
            file=sys.stderr,
        )
    else:
        print(f"\n[{words} words]", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _add_header_flags(p: argparse.ArgumentParser) -> None:
    """Saved transcripts start with Sori's three-line header (title, show and
    date, source); these override what the source reported."""
    p.add_argument("--title", help="header title (default: what the source reports)")
    p.add_argument("--show", help="header show name")
    p.add_argument("--date", help="header date, YYYY-MM-DD")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="transcribe.py",
        description="Get a transcript from a podcast episode — free, local, no API key.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List episodes in a podcast's RSS feed")
    p_list.add_argument("feed_url")
    p_list.add_argument("--search", help="Filter by title substring")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list)

    p_yt = sub.add_parser("youtube", help="Transcript from a YouTube video's captions")
    p_yt.add_argument("url")
    p_yt.add_argument("--out", help="Output .txt path (default: print to stdout)")
    p_yt.add_argument("--lang", default="en")
    _add_header_flags(p_yt)
    p_yt.set_defaults(func=cmd_youtube)

    p_audio = sub.add_parser("audio", help="Transcribe an MP3 URL or local file with local Whisper")
    p_audio.add_argument("url_or_path")
    p_audio.add_argument("--out", help="Output .txt path (default: print to stdout)")
    p_audio.add_argument(
        "--model", default="base.en",
        help="Whisper model size (default: base.en). Drop the .en suffix for non-English audio.",
    )
    p_audio.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    _add_header_flags(p_audio)
    p_audio.set_defaults(func=cmd_audio)

    p_ep = sub.add_parser("episode", help="Find an episode in an RSS feed and transcribe it in one step")
    p_ep.add_argument("feed_url")
    p_ep.add_argument("search", help="Episode title (or part of it) to search for")
    p_ep.add_argument("--out", help="Output .txt path (default: <episode-title>.txt)")
    p_ep.add_argument("--model", default="base.en")
    p_ep.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    _add_header_flags(p_ep)
    p_ep.set_defaults(func=cmd_episode)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
