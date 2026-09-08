#!/usr/bin/env python3
"""
Sori — a small desktop app around podcast-transcriber.

Subscribe to podcast RSS feeds and YouTube channels, see what's new, and turn
episodes into text files. Same two free paths as the CLI: YouTube captions for
video shows, local Whisper for audio. No API key, nothing leaves the machine
except the feed/audio fetches themselves.

One more step is optional, and it is NOT free: turning a transcript into a
training deck + study guide. Whisper only converts speech to text — writing
a training needs a language model, so that one step calls the Claude API
(a key entered in Settings) and costs money per run. Everything else in the
app stays exactly as free/local as it always was; see training.py and
deck_render.py for that boundary.

Two ways to run, plus two CLIs over the same store:
    py app.py            open the window (ui/index.html, pywebview)
    py app.py --sweep    headless: check every show, transcribe new episodes
                         for shows marked auto (and generate trainings for
                         shows marked Auto-train), print a summary, exit
    py shows.py ...      subscriptions and folders from a shell (list, add,
                         remove, auto, auto-train, folder, check)
    py settings.py ...   model, lang, transcripts-dir, deck-theme, api-key
                         (the key comes from ANTHROPIC_API_KEY, never argv)

All state lives under %USERPROFILE%\\Sori (never inside the app folder, which
may be read-only when installed from the packaged EXE). The folder was called
PodcastStudio before the rename; state_dir() migrates it automatically:
    shows.json                     subscriptions + per-show seen markers
    credentials.json                Claude API key (never logged, never synced)
    Transcripts/<Show>/<date> - <title>.txt
    Trainings/<Show>/<date> - <title>.pptx (+ matching .md study guide)
    sweep.log                      append-only log of headless runs

The JS bridge (class Api) is the only surface the UI touches. Every method
returns {"ok": True, "data": ...} or {"ok": False, "error": "..."} — the UI
never sees an exception, and a dead network degrades to an error string.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
import queue
import re
import sys
import tempfile
import threading
import time
import traceback
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import transcribe as tx
import training as tr

APP_NAME = "Sori"
YT_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
# How many entries deep to look when deciding what's new. Feeds can be
# thousands of items long; nobody is catching up on 1,000 episodes.
FEED_WINDOW = 25
# Total tries an episode gets on its own: the first attempt plus two automatic
# retries on later polls. After that it is parked until someone hits Retry —
# a feed that 404s forever must not burn the queue every hour.
MAX_ATTEMPTS = 3
# Feeds are network-bound, so check them concurrently; a small pool keeps a
# 20-show list quick without looking like a scraper.
FEED_WORKERS = 4


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def state_dir() -> Path:
    """Root of all app state. SORI_HOME overrides (used by tests).

    This folder was called PodcastStudio through the Earshot rebrand — the
    name survived both renames because it holds live user data. If the old
    folder exists and the new one doesn't, it is renamed in place so a
    returning user keeps every show, transcript, and training. A migration
    that fails is not fatal: we keep working from the old location rather
    than silently start empty and orphan the data.
    """
    override = os.environ.get("SORI_HOME") or os.environ.get("PODCAST_STUDIO_HOME")
    if override:
        root = Path(override)
        root.mkdir(parents=True, exist_ok=True)
        return root

    root = Path.home() / "Sori"
    legacy = Path.home() / "PodcastStudio"
    if not root.exists() and legacy.exists():
        try:
            legacy.rename(root)
        except OSError:
            return legacy
    root.mkdir(parents=True, exist_ok=True)
    return root


def shows_path() -> Path:
    return state_dir() / "shows.json"


def credentials_path() -> Path:
    """Separate from shows.json on purpose: the API key must never ride along
    with a store dump, an export, or a debug print of settings."""
    return state_dir() / "credentials.json"


def trainings_dir() -> Path:
    d = transcripts_dir().parent / "Trainings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_credentials() -> dict:
    path = credentials_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_credentials(data: dict) -> None:
    path = credentials_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def anthropic_api_key() -> str | None:
    return (load_credentials().get("anthropic_api_key") or "").strip() or None


def transcripts_dir() -> Path:
    """Where transcripts land — the settings override if one is set, else the default."""
    override = None
    try:
        override = load_store()["settings"].get("transcripts_dir")
    except Exception:
        override = None
    d = Path(override) if override else state_dir() / "Transcripts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def app_dir() -> Path:
    """Folder holding ui/ — differs between source runs and the frozen EXE."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def _safe_name(text: str, limit: int = 90) -> str:
    """Filename-safe on Windows: strip <>:"/\\|?* and trailing dots/spaces."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned).rstrip(". ")
    return (cleaned[:limit].rstrip(". ") or "untitled")


# ---------------------------------------------------------------------------
# Store — shows.json read/write
# ---------------------------------------------------------------------------

_store_lock = threading.RLock()

DEFAULT_SETTINGS = {"model": "base.en", "device": "cpu", "lang": "en", "transcripts_dir": None,
                     "deck_theme": "baek"}
# Every store has this bucket; shows never point at nothing.
UNSORTED_FOLDER = {"id": "unsorted", "name": "Unsorted"}


def _fresh_store() -> dict:
    return {"version": 2, "settings": dict(DEFAULT_SETTINGS), "shows": [],
            "folders": [dict(UNSORTED_FOLDER)]}


def load_store() -> dict:
    with _store_lock:
        path = shows_path()
        if not path.exists():
            return _fresh_store()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # A corrupt file must not brick the app; move it aside and restart clean.
            try:
                path.replace(path.with_suffix(".json.bad"))
            except OSError:
                pass
            return _fresh_store()
        data.setdefault("version", 1)
        data.setdefault("shows", [])
        settings = dict(DEFAULT_SETTINGS)
        settings.update(data.get("settings") or {})
        data["settings"] = settings
        for show in data["shows"]:
            show.setdefault("auto", False)
            show.setdefault("auto_train", False)
            show.setdefault("seen", [])
            show.setdefault("type", "rss")
            if not isinstance(show.get("failures"), dict):
                show["failures"] = {}

        # v1 -> v2: source folders. "unsorted" always exists; a show pointing
        # at a folder that's gone (or that never had one) falls back into it.
        folders = data.get("folders")
        if not isinstance(folders, list):
            folders = []
        if not any(f.get("id") == "unsorted" for f in folders):
            folders.insert(0, dict(UNSORTED_FOLDER))
        data["folders"] = folders
        folder_ids = {f["id"] for f in folders}
        for show in data["shows"]:
            show.setdefault("folder", "unsorted")
            if show["folder"] not in folder_ids:
                show["folder"] = "unsorted"
        data["version"] = 2
        return data


def save_store(data: dict) -> None:
    with _store_lock:
        path = shows_path()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)


def _same_show_name(a: str, b: str) -> bool:
    """True when two subscription names look like the same show.

    Podcast names are usually "Title: subtitle" or "Title - subtitle", and the
    subtitle is what differs between a show's RSS feed and its YouTube channel
    ("The AI Daily Brief: ... News" vs "The AI Daily Brief: ... News and
    Analysis"). Compare the title before the first separator, normalized. A
    plain prefix rule would also flag "The Daily" against "The Daily Show",
    which are different shows, so this deliberately stays narrow.
    """
    def core(s: str) -> str:
        head = re.split(r"\s*[:|—–]\s*|\s+-\s+", s or "", maxsplit=1)[0]
        return re.sub(r"[^a-z0-9]+", " ", head.lower()).strip()
    x, y = core(a), core(b)
    return bool(x) and x == y


def _find_show(data: dict, show_id: str) -> dict | None:
    return next((s for s in data["shows"] if s["id"] == show_id), None)


def _push_seen(show: dict, episode_id: str) -> None:
    seen = show.setdefault("seen", [])
    if episode_id not in seen:
        seen.append(episode_id)
    # Keep the marker list bounded — it only needs to cover the feed window.
    del seen[:-400]


def _mark_seen(show_id: str, episode_id: str) -> None:
    """Retire an episode: it succeeded, so stop offering it and forget its failures."""
    with _store_lock:
        data = load_store()
        show = _find_show(data, show_id)
        if not show:
            return
        _push_seen(show, episode_id)
        show.get("failures", {}).pop(episode_id, None)
        show["last_seen"] = episode_id
        save_store(data)


def _record_failure(show_id: str, episode_id: str, error: str) -> int:
    """Count one failed attempt; returns the running total.

    Below MAX_ATTEMPTS the episode stays unseen, so the next poll picks it up
    again — transient things (a flaky CDN, a caption track that lands an hour
    after the video) heal themselves. At MAX_ATTEMPTS it is marked seen and
    only a manual Retry brings it back.
    """
    with _store_lock:
        data = load_store()
        show = _find_show(data, show_id)
        if not show:
            return MAX_ATTEMPTS
        failures = show.setdefault("failures", {})
        entry = failures.get(episode_id) or {}
        attempts = int(entry.get("attempts") or 0) + 1
        failures[episode_id] = {
            "attempts": attempts,
            "error": str(error)[:500],
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        if attempts >= MAX_ATTEMPTS:
            _push_seen(show, episode_id)
        # Bound the record alongside `seen`; stale entries are pure noise.
        if len(failures) > 200:
            for key in list(failures)[:-200]:
                failures.pop(key, None)
        save_store(data)
        return attempts


def _clear_failure(show_id: str, episode_id: str) -> None:
    """Manual Retry: forget the history and un-retire the episode."""
    with _store_lock:
        data = load_store()
        show = _find_show(data, show_id)
        if not show:
            return
        show.get("failures", {}).pop(episode_id, None)
        seen = show.get("seen") or []
        if episode_id in seen:
            seen.remove(episode_id)
        save_store(data)


# ---------------------------------------------------------------------------
# Feed resolution + parsing
# ---------------------------------------------------------------------------

def _yt_channel_feed(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def _yt_playlist_feed(playlist_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"


def _resolve_youtube(url: str) -> str:
    """Turn any YouTube channel/handle/playlist URL into its RSS feed URL.

    Cheap string paths first; yt_dlp metadata extraction only for handles and
    vanity URLs, where the channel id genuinely isn't in the URL.
    """
    if "feeds/videos.xml" in url:
        return url

    m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", url) or re.search(
        r"youtube\.com/playlist/?\?.*list=([A-Za-z0-9_-]+)", url
    )
    if m:
        return _yt_playlist_feed(m.group(1))

    m = re.search(r"youtube\.com/channel/(UC[A-Za-z0-9_-]{20,})", url)
    if m:
        return _yt_channel_feed(m.group(1))

    # @handle, /c/name, /user/name, or a plain video URL — ask yt_dlp once.
    try:
        import yt_dlp
    except ImportError as exc:  # pragma: no cover - packaging guarantees this
        raise RuntimeError("yt-dlp is not installed, so YouTube shows can't be added.") from exc

    probe = url
    if re.match(r"^@[\w.-]+$", url.strip()):
        probe = f"https://www.youtube.com/{url.strip()}"

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "playlist_items": "1",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(probe, download=False)

    channel_id = info.get("channel_id") or info.get("uploader_id") or ""
    if not channel_id and info.get("entries"):
        first = info["entries"][0] or {}
        channel_id = first.get("channel_id") or ""
    if not channel_id.startswith("UC"):
        raise RuntimeError("Couldn't work out the YouTube channel for that link.")
    return _yt_channel_feed(channel_id)


def _looks_like_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url or url.strip().startswith("@")


def _iso_date(raw: str) -> str:
    """Best-effort YYYY-MM-DD out of an RSS pubDate or an Atom timestamp."""
    raw = (raw or "").strip()
    if not raw:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return parsedate_to_datetime(raw).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        pass
    m = re.match(r"(\d{4}-\d{2}-\d{2})", raw)
    return m.group(1) if m else datetime.now(timezone.utc).strftime("%Y-%m-%d")


def parse_feed(feed_url: str, kind: str) -> tuple[str, list[dict]]:
    """Fetch a feed. Returns (show_name, episodes newest-first).

    Episodes are UI-shaped: {id, title, url, date, kind}.
    """
    root = ET.fromstring(tx.fetch_xml(feed_url))

    if kind == "youtube":
        name_el = root.find("atom:title", YT_NS)
        name = (name_el.text or "").strip() if name_el is not None else "YouTube channel"
        episodes = []
        for entry in root.findall("atom:entry", YT_NS):
            vid_el = entry.find("yt:videoId", YT_NS)
            title_el = entry.find("atom:title", YT_NS)
            pub_el = entry.find("atom:published", YT_NS)
            if vid_el is None or not vid_el.text:
                continue
            episodes.append({
                "id": vid_el.text.strip(),
                "title": (title_el.text or "").strip() if title_el is not None else "",
                "url": f"https://www.youtube.com/watch?v={vid_el.text.strip()}",
                "date": _iso_date(pub_el.text if pub_el is not None else ""),
                "kind": "youtube",
            })
        return name, episodes

    title_el = root.find("./channel/title")
    name = (title_el.text or "").strip() if title_el is not None else "Podcast"
    episodes = [
        {
            "id": e["guid"],
            "title": e["title"],
            "url": e["mp3_url"],
            "date": _iso_date(e["pub_date"]),
            "kind": "mp3",
            "duration": e.get("duration"),
        }
        for e in tx.parse_rss_episodes(root)
    ]
    return name, episodes


def new_episodes_for(show: dict) -> list[dict]:
    """Episodes in this show's feed window that haven't been seen yet."""
    _name, episodes = parse_feed(show["feed_url"], show["type"])
    seen = set(show.get("seen") or [])
    failures = show.get("failures") or {}
    fresh = []
    for ep in episodes[:FEED_WINDOW]:
        if ep["id"] in seen:
            continue
        item = {**ep, "show_id": show["id"], "show_name": show["name"]}
        past = failures.get(ep["id"])
        if past:
            # Carry the failure forward so the UI can say "failed, 1 try left"
            # instead of silently re-offering an episode that just broke.
            item["attempts"] = past.get("attempts", 0)
            item["last_error"] = past.get("error")
        fresh.append(item)
    return fresh


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------

class TranscriptionError(Exception):
    """A transcription that failed for a reportable reason (no captions, 404...)."""


def transcript_path_for(show_name: str, episode: dict) -> Path:
    folder = transcripts_dir() / _safe_name(show_name, 60)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{episode.get('date', 'undated')} - {_safe_name(episode.get('title', ''))}.txt"


def run_transcription(show: dict, episode: dict, settings: dict, on_progress=None, cancel=None) -> Path:
    """Produce one transcript file (+ a `.json` segment sidecar for the Reader).

    Raises TranscriptionError on a clean failure, tx.TranscriptionCancelled if
    `cancel` is set mid-run.
    """
    def report(stage: str, fraction=None):
        if on_progress:
            on_progress(stage, fraction)

    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise tx.TranscriptionCancelled()

    out = transcript_path_for(show["name"], episode)
    if out.exists() and out.stat().st_size > 0:
        report("done", 1.0)
        return out

    check_cancel()
    model_name = "captions"
    duration = None
    started = time.monotonic()

    if episode.get("kind") == "youtube":
        report("captions", None)
        cap_lang = settings.get("lang", "en")
        try:
            segments = tx.fetch_youtube_caption_segments(
                episode["url"], cap_lang if cap_lang != "auto" else "en",
            )
        except ImportError as exc:
            raise TranscriptionError("yt-dlp isn't installed, so captions can't be fetched.") from exc
        except Exception as exc:
            raise TranscriptionError(f"Couldn't reach YouTube: {exc}") from exc
        if not segments:
            raise TranscriptionError("This video has no captions yet.")
        check_cancel()
        text = " ".join(s["text"] for s in segments)
    else:
        model_name = settings.get("model", "base.en")
        device = settings.get("device", "cpu")
        raw_lang = settings.get("lang")
        # English stays auto/forced-by-model; "ko" (etc.) only reaches
        # multilingual models like large-v3 — a .en model can't take it.
        language = None if (raw_lang in (None, "auto", "en") or model_name.endswith(".en")) else raw_lang
        with tempfile.TemporaryDirectory() as tmp:
            report("downloading", 0.0)
            try:
                audio = tx._download_audio(
                    episode["url"], Path(tmp),
                    on_progress=lambda f: report("downloading", f),
                    cancel=cancel,
                )
            except tx.TranscriptionCancelled:
                raise
            except Exception as exc:
                raise TranscriptionError(f"Couldn't download the audio: {exc}") from exc

            check_cancel()
            # First run on a machine fetches ~150MB of Whisper weights. That
            # used to look like a hang, so load the model as its own visible
            # step; afterwards it's cached and this returns instantly.
            try:
                if not tx.whisper_model_is_cached(model_name, device):
                    report("downloading model", None)
                tx.load_whisper_model(model_name, device)
            except ImportError as exc:
                raise TranscriptionError(
                    "faster-whisper isn't installed, so audio can't be transcribed."
                ) from exc
            except Exception as exc:
                raise TranscriptionError(f"Couldn't load the Whisper model: {exc}") from exc

            check_cancel()
            report("transcribing", 0.0)
            try:
                segments, duration = tx._transcribe_whisper_segments(
                    audio, model_name, device,
                    on_progress=lambda f: report("transcribing", f),
                    cancel=cancel, language=language,
                )
            except tx.TranscriptionCancelled:
                raise
            except Exception as exc:
                raise TranscriptionError(f"Transcription failed: {exc}") from exc
        text = " ".join(s["text"] for s in segments)
        if not text.strip():
            raise TranscriptionError("Whisper returned an empty transcript.")

    header = f"{episode.get('title', '')}\n{show['name']} — {episode.get('date', '')}\n{episode.get('url', '')}\n\n"
    out.write_text(header + text, encoding="utf-8")

    sidecar = {
        "meta": {
            "title": episode.get("title", ""),
            "show": show["name"],
            "date": episode.get("date", ""),
            "url": episode.get("url", ""),
            "model": model_name,
            "duration": duration,
            "elapsed": round(time.monotonic() - started, 1),
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        "segments": segments,
    }
    out.with_suffix(".json").write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=None), encoding="utf-8",
    )
    report("done", 1.0)
    return out


# ---------------------------------------------------------------------------
# Training generation — transcript -> Claude -> deck + study guide
# ---------------------------------------------------------------------------
#
# Unlike transcription, this step is NOT free/local: it calls the Claude API,
# which needs a key (Settings) and costs money per run. Whisper only converts
# speech to text; writing a training deck is a language-model job the app
# had nowhere else to do it. See README.md for the honest trade-off.

class TrainingError(Exception):
    """A training generation that failed for a reportable reason (no API
    key, a bad transcript, a render failure...)."""


def training_paths_for(show_name: str, episode: dict) -> tuple[Path, Path]:
    folder = trainings_dir() / _safe_name(show_name, 60)
    folder.mkdir(parents=True, exist_ok=True)
    base = folder / f"{episode.get('date', 'undated')} - {_safe_name(episode.get('title', ''))}"
    # Not with_suffix(): a title like "Ep. 12" would be cut at its last dot,
    # and two such episodes would share one deck.
    return base.with_name(base.name + ".pptx"), base.with_name(base.name + ".md")


def run_training(show: dict, episode: dict, transcript_path: Path, settings: dict,
                  on_progress=None, cancel=None) -> tuple[Path, Path]:
    """Produce one `.pptx` deck + one `.md` study guide from an existing transcript.

    Raises TrainingError on a clean failure, tx.TranscriptionCancelled if
    `cancel` is set mid-run (same cancel primitive as transcription — one
    cooperative-cancel contract across both job types).
    """
    def report(stage: str, fraction=None):
        if on_progress:
            on_progress(stage, fraction)

    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise tx.TranscriptionCancelled()

    pptx_path, md_path = training_paths_for(show["name"], episode)
    if pptx_path.exists() and md_path.exists():
        report("done", 1.0)
        return pptx_path, md_path

    api_key = anthropic_api_key()
    if not api_key:
        raise TrainingError("No Claude API key set — add one in Settings first.")
    if not transcript_path.exists():
        raise TrainingError("The transcript for this episode is missing.")

    check_cancel()
    report("writing", None)
    transcript_text = transcript_path.read_text(encoding="utf-8")
    try:
        result = tr.generate_training(
            transcript_text=transcript_text,
            meta={"title": episode.get("title", ""), "show": show["name"],
                  "date": episode.get("date", "")},
            api_key=api_key,
        )
    except tr.TrainingGenerationError as exc:
        raise TrainingError(str(exc)) from exc

    check_cancel()
    report("rendering", None)
    theme = settings.get("deck_theme", "baek")
    try:
        import deck_render
        deck_render.render_pptx(result.outline, theme, pptx_path)
    except tr.TrainingGenerationError:
        raise
    except Exception as exc:
        raise TrainingError(f"Couldn't render the deck: {exc}") from exc

    md_path.write_text(result.study_guide_md, encoding="utf-8")
    report("done", 1.0)
    return pptx_path, md_path


class TrainWorker:
    """Serial training-generation queue — mirrors Worker's shape exactly.

    A separate queue/thread from transcription on purpose: training is a
    paid API call and a CPU-heavy pptx render, and must never block (or be
    blocked by) the free local transcription queue.
    """

    def __init__(self, emit):
        self._q: queue.Queue = queue.Queue()
        self._emit = emit
        self._states: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._queued: set[str] = set()
        self._cancels: dict[str, threading.Event] = {}
        self._running: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="trainer", daemon=True)
        self._thread.start()

    def states(self) -> dict:
        with self._lock:
            return {k: dict(v) for k, v in self._states.items()}

    def _set(self, episode_id: str, **fields) -> None:
        with self._lock:
            entry = self._states.setdefault(episode_id, {"id": episode_id})
            entry.update(fields)
            snapshot = dict(entry)
        self._emit("trainjob", snapshot)

    def submit(self, show: dict, episode: dict, transcript_path: Path, settings: dict) -> str:
        eid = episode["id"]
        with self._lock:
            event = self._cancels.get(eid)
            if event is None:
                self._cancels[eid] = threading.Event()
            else:
                event.clear()
            if eid in self._queued:
                return "already queued"
            self._queued.add(eid)
            self._states[eid] = {"id": eid}
        self._set(eid, status="queued", progress=None, title=episode.get("title"),
                  show_id=show["id"], show_name=show.get("name"), error=None)
        self._q.put((show, episode, transcript_path, settings))
        self.start()
        return "queued"

    def cancel(self, eid: str) -> str:
        with self._lock:
            event = self._cancels.get(eid)
            if event is None:
                return "not queued"
            state = self._states.get(eid)
            if state and state.get("status") in ("done", "failed", "cancelled"):
                return "finished"
            event.set()
            queued_only = eid in self._queued and eid != self._running
        if queued_only:
            self._set(eid, status="cancelled", progress=None, error=None)
        return "cancelling"

    def pending(self) -> int:
        return self._q.qsize()

    def _loop(self) -> None:
        while True:
            show, episode, transcript_path, settings = self._q.get()
            eid = episode["id"]
            event = self._cancels.get(eid)
            if event is not None and event.is_set():
                self._set(eid, status="cancelled", progress=None, error=None)
                with self._lock:
                    self._queued.discard(eid)
                self._q.task_done()
                continue
            with self._lock:
                self._running = eid
            try:
                def report(stage, frac=None):
                    self._set(eid, status=stage, progress=frac)

                pptx_path, md_path = run_training(
                    show, episode, transcript_path, settings,
                    on_progress=report, cancel=event,
                )
                self._set(eid, status="done", progress=1.0,
                          pptx_path=str(pptx_path), md_path=str(md_path), error=None)
            except tx.TranscriptionCancelled:
                self._set(eid, status="cancelled", progress=None, error=None)
            except Exception as exc:
                message = str(exc) if isinstance(exc, TrainingError) else f"Unexpected error: {exc}"
                if not isinstance(exc, TrainingError):
                    traceback.print_exc()
                self._set(eid, status="failed", progress=None, error=message)
            finally:
                with self._lock:
                    self._queued.discard(eid)
                    self._running = None
                    if len(self._states) > 200:
                        for key in list(self._states)[:-200]:
                            if key in self._queued:
                                continue
                            self._states.pop(key, None)
                            self._cancels.pop(key, None)
                self._q.task_done()


# ---------------------------------------------------------------------------
# Worker — one episode at a time, in the background
# ---------------------------------------------------------------------------

class Worker:
    """Serial transcription queue. One job at a time keeps CPU sane on laptops."""

    # Hand-picked episodes run before anything the hourly poll pushed in on
    # its own. Ties keep arrival order (the sequence number), and the payload
    # is never compared because the tuple is decided before it is reached.
    PRIORITY_MANUAL = 0
    PRIORITY_AUTO = 1

    def __init__(self, emit, on_transcribed=None):
        self._q: queue.PriorityQueue = queue.PriorityQueue()
        self._seq = itertools.count()
        self._emit = emit
        self._on_transcribed = on_transcribed  # (show, episode, path) -> None, for auto-train chaining
        self._states: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._queued: set[str] = set()
        self._cancels: dict[str, threading.Event] = {}
        self._running: str | None = None
        # Dismissed = "never show me this again". A cancel alone leaves a
        # `cancelled` snapshot behind that the UI re-renders as a fresh row on
        # its next poll; a dismissed id is dropped from the job table instead.
        self._dismissed: set[str] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="transcriber", daemon=True)
        self._thread.start()

    def states(self) -> dict:
        with self._lock:
            return {k: dict(v) for k, v in self._states.items()}

    def _set(self, episode_id: str, **fields) -> None:
        with self._lock:
            entry = self._states.setdefault(episode_id, {"id": episode_id})
            entry.update(fields)
            snapshot = dict(entry)
        self._emit("job", snapshot)

    def _reporter(self, episode_id: str):
        """Progress callback that throttles the bridge.

        Whisper emits a segment every second or two and the downloader fires
        per 256KB chunk; pushing every one of those across evaluate_js makes
        the window stutter for no visible gain. Stage changes and the final
        frame always go through — only mid-stage ticks are rate-limited.
        """
        last = {"t": 0.0, "frac": -1.0, "stage": None}

        def report(stage: str, frac=None) -> None:
            now = time.monotonic()
            moved = frac is not None and (frac - last["frac"]) >= 0.01
            if (stage != last["stage"] or frac is None or frac >= 1.0
                    or (moved and now - last["t"] >= 0.25)):
                last["t"] = now
                last["stage"] = stage
                if frac is not None:
                    last["frac"] = frac
                self._set(episode_id, status=stage, progress=frac)

        return report

    def submit(self, show: dict, episode: dict, settings: dict,
               priority: int = PRIORITY_AUTO) -> str:
        eid = episode["id"]
        with self._lock:
            # Re-arm the cancel event FIRST: if a prior cancel is still
            # pending on this id, a fresh submit must not inherit it — the
            # "already queued" short-circuit below would otherwise drop this
            # request and it'd surface as cancelled without ever running.
            event = self._cancels.get(eid)
            if event is None:
                self._cancels[eid] = threading.Event()
            else:
                event.clear()
            # A fresh submit after a dismiss is a deliberate choice; honour it.
            self._dismissed.discard(eid)
            if eid in self._queued:
                return "already queued"
            self._queued.add(eid)
            # Replace, don't merge: a re-submitted episode must not inherit the
            # previous run's error text or path.
            self._states[eid] = {"id": eid}
        # Carry enough of the episode in the snapshot that the UI can render
        # (and re-queue) a row for a job whose episode left the feed window —
        # local file imports have no feed row at all.
        self._set(eid, status="queued", progress=None, title=episode.get("title"),
                  show_id=show["id"], show_name=show.get("name"),
                  url=episode.get("url"), kind=episode.get("kind"), error=None)
        self._q.put((priority, next(self._seq), (show, episode, settings)))
        self.start()
        return "queued"

    def cancel(self, eid: str) -> str:
        """Stop a queued or in-flight job. Returns 'cancelling', 'not queued', or 'finished'."""
        with self._lock:
            event = self._cancels.get(eid)
            if event is None:
                return "not queued"
            state = self._states.get(eid)
            if state and state.get("status") in ("done", "failed", "cancelled"):
                return "finished"
            event.set()
            queued_only = eid in self._queued and eid != self._running
        if queued_only:
            self._set(eid, status="cancelled", progress=None, error=None, cancelling=False)
        else:
            self._set(eid, cancelling=True)
        return "cancelling"

    def dismiss(self, eid: str) -> str:
        """Forget an episode: stop any job on it and drop its row from the job table.

        Returns 'dismissed' (gone now) or 'stopping' (mid-run; the loop drops
        it the moment Whisper notices the cancel). Marking the episode seen in
        the store is the caller's job — that is what keeps the next feed check
        from offering it again.
        """
        with self._lock:
            running = eid == self._running
            queued = eid in self._queued
            event = self._cancels.get(eid)
            if not queued and not running:
                # Nothing in flight: a stale done/failed/cancelled snapshot is
                # all that keeps the row alive. Drop it.
                self._states.pop(eid, None)
                self._cancels.pop(eid, None)
                gone = True
            else:
                self._dismissed.add(eid)
                if event is not None:
                    event.set()
                if not running:
                    # Hide the row now; _loop skips the entry when it dequeues it.
                    self._states.pop(eid, None)
                gone = not running
        if gone:
            self._emit("job", {"id": eid, "status": "dismissed"})
        else:
            self._set(eid, cancelling=True)  # same shape cancel() emits, so no orphan row
        return "dismissed" if gone else "stopping"

    def _drop_if_dismissed(self, eid: str) -> bool:
        """Finish a dismiss from inside the loop. True if the id was dismissed."""
        with self._lock:
            if eid not in self._dismissed:
                return False
            self._dismissed.discard(eid)
            self._states.pop(eid, None)
            self._cancels.pop(eid, None)
        self._emit("job", {"id": eid, "status": "dismissed"})
        return True

    def pending(self) -> int:
        return self._q.qsize()

    def _loop(self) -> None:
        while True:
            _priority, _seq, (show, episode, settings) = self._q.get()
            eid = episode["id"]
            event = self._cancels.get(eid)
            if event is not None and event.is_set():
                # Cancelled before it ever started — never call run_transcription.
                with self._lock:
                    self._queued.discard(eid)
                if not self._drop_if_dismissed(eid):
                    self._set(eid, status="cancelled", progress=None, error=None)
                self._q.task_done()
                self._emit("queue", {"pending": self._q.qsize()})
                continue
            with self._lock:
                self._running = eid
            try:
                path = run_transcription(
                    show, episode, settings, on_progress=self._reporter(eid), cancel=event,
                )
                self._set(eid, status="done", progress=1.0, path=str(path), error=None,
                          attempts=0, retries_left=0)
                _mark_seen(show["id"], eid)
                if self._on_transcribed is not None:
                    try:
                        self._on_transcribed(show, episode, path)
                    except Exception:
                        traceback.print_exc()  # auto-train must never take down transcription
            except tx.TranscriptionCancelled:
                if not self._drop_if_dismissed(eid):
                    self._set(eid, status="cancelled", progress=None, error=None, cancelling=False)
            except Exception as exc:
                if isinstance(exc, TranscriptionError):
                    message = str(exc)
                else:  # pragma: no cover - last-resort net
                    message = f"Unexpected error: {exc}"
                    traceback.print_exc()
                attempts = _record_failure(show["id"], eid, message)
                self._set(eid, status="failed", progress=None, error=message,
                          attempts=attempts,
                          retries_left=max(MAX_ATTEMPTS - attempts, 0))
            finally:
                with self._lock:
                    self._queued.discard(eid)
                    self._running = None
                    # Bound the in-memory job tables — a long-lived session
                    # must not grow these forever. Same trim shape as the
                    # `failures` dict in _record_failure, but a job still in
                    # self._queued must never be evicted here — its cancel
                    # Event is load-bearing for that pending submit.
                    if len(self._states) > 200:
                        for key in list(self._states)[:-200]:
                            if key in self._queued:
                                continue
                            self._states.pop(key, None)
                            self._cancels.pop(key, None)
                self._q.task_done()
                self._emit("queue", {"pending": self._q.qsize()})


# ---------------------------------------------------------------------------
# Bridge API — everything the UI can call
# ---------------------------------------------------------------------------

def bridge(func):
    """Wrap a bridge method so the UI always gets {ok, data|error}, never a throw."""
    def wrapper(*args, **kwargs):
        try:
            return {"ok": True, "data": func(*args, **kwargs)}
        except Exception as exc:
            traceback.print_exc()
            return {"ok": False, "error": str(exc) or exc.__class__.__name__}
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    return wrapper


# ---------------------------------------------------------------------------
# Transcript reading + export — shared by the read_transcript/export_transcript
# bridge methods below.
# ---------------------------------------------------------------------------

VALID_MODELS = {"tiny.en", "base.en", "small.en", "large-v3"}
VALID_LANGS = {"auto", "en", "ko"}


def _confine_to_transcripts(path: str) -> Path:
    """Confinement rule shared by read_transcript/export_transcript/open_transcript.

    Accepts a path under the CURRENT transcripts dir or the default one — a
    transcript written before a folder change (see choose_folder) stays
    openable in the common case instead of looking deleted.
    """
    target = Path(path).resolve()
    roots = {transcripts_dir().resolve(), (state_dir() / "Transcripts").resolve()}
    if not any(root in target.parents for root in roots):
        raise ValueError("That file isn't in your transcripts folder.")
    if not target.exists():
        raise ValueError("That transcript no longer exists.")
    return target


def _confine_to_trainings(path: str) -> Path:
    target = Path(path).resolve()
    root = trainings_dir().resolve()
    if root not in target.parents:
        raise ValueError("That file isn't in your trainings folder.")
    if not target.exists():
        raise ValueError("That file no longer exists.")
    return target


def _read_transcript_data(target: Path) -> dict:
    """The sidecar if one exists; otherwise a single-segment shape parsed from the .txt."""
    sidecar = target.with_suffix(".json")
    if sidecar.exists():
        try:
            return json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass  # corrupt sidecar — fall through to the legacy .txt parse below
    raw = target.read_text(encoding="utf-8")
    header, _, body = raw.partition("\n\n")
    header_lines = header.splitlines()
    title = header_lines[0] if len(header_lines) > 0 else ""
    show_date = header_lines[1] if len(header_lines) > 1 else ""
    url = header_lines[2] if len(header_lines) > 2 else ""
    show, sep, date = show_date.partition(" — ")
    if not sep:
        show, date = show_date, ""
    return {
        "meta": {"title": title, "show": show, "date": date, "url": url},
        "segments": [{"start": 0, "end": None, "text": body}],
        "legacy": True,
    }


def _srt_timestamp(seconds: float) -> str:
    ms = round(max(seconds, 0.0) * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _render_srt(segments: list[dict]) -> str:
    blocks = []
    for i, seg in enumerate(segments, start=1):
        start = seg.get("start") or 0.0
        end = seg.get("end")
        if end is None:
            end = start + 4.0  # no real end time — give it a readable-length card
        blocks.append(
            f"{i}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{(seg.get('text') or '').strip()}\n"
        )
    return "\n".join(blocks)


def _render_md(meta: dict, segments: list[dict], legacy: bool) -> str:
    lines = [f"# {meta.get('title', '')}", ""]
    meta_line = " · ".join(x for x in (meta.get("show"), meta.get("date"), meta.get("url")) if x)
    if meta_line:
        lines.append(meta_line)
        lines.append("")
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        if legacy or seg.get("start") is None:
            lines.append(text)
        else:
            m, s = divmod(int(seg["start"]), 60)
            lines.append(f"**[{m:02d}:{s:02d}]** {text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


class Api:
    """Bridge object handed to pywebview as js_api.

    Every attribute is underscore-prefixed on purpose: pywebview walks the
    public attributes of this object to build the JS proxy, and a public
    handle back to the Window sends that walk into infinite recursion.
    """

    def __init__(self):
        self._window = None
        self._worker = Worker(self._emit, on_transcribed=self._maybe_auto_train)
        self._trainer = TrainWorker(self._emit)
        self._stop = threading.Event()

    def _maybe_auto_train(self, show: dict, episode: dict, transcript_path: Path) -> None:
        """Called by Worker right after a successful transcription. Chains
        into the training queue only if this show has Auto-train on — a
        manual "Generate Training" click is the default path."""
        data = load_store()
        current = _find_show(data, show["id"])
        if current and current.get("auto_train"):
            self._trainer.submit(show, episode, transcript_path, data["settings"])

    def _attach(self, window) -> None:
        self._window = window

    # -- event push ---------------------------------------------------------

    def _emit(self, name: str, payload: dict) -> None:
        if self._window is None:
            return
        try:
            self._window.evaluate_js(
                f"window.studioEvent && window.studioEvent({json.dumps(name)},{json.dumps(payload)})"
            )
        except Exception:
            pass  # window closed mid-flight; nothing to do

    # -- shows --------------------------------------------------------------

    @bridge
    def list_shows(self) -> list[dict]:
        return [
            {k: s.get(k) for k in
             ("id", "name", "type", "feed_url", "auto", "auto_train", "added_at",
              "last_checked", "folder")}
            for s in load_store()["shows"]
        ]

    @bridge
    def add_show(self, url: str) -> dict:
        url = (url or "").strip()
        if not url:
            raise ValueError("Paste a feed URL or a YouTube channel first.")

        if _looks_like_youtube(url):
            kind = "youtube"
            feed_url = _resolve_youtube(url)
        elif re.match(r"^https?://", url):
            kind = "rss"
            feed_url = url
        else:
            raise ValueError("That doesn't look like a link. Paste an RSS URL or a YouTube channel.")

        if any(s["feed_url"] == feed_url for s in load_store()["shows"]):
            raise ValueError("That show is already in your list.")

        try:
            name, episodes = parse_feed(feed_url, kind)
        except ET.ParseError as exc:
            raise ValueError("That link didn't return a readable feed.") from exc
        except Exception as exc:
            raise ValueError(f"Couldn't read that feed: {exc}") from exc

        if not episodes:
            raise ValueError("That feed has no episodes in it.")

        # Same show through two doors (its RSS feed AND its YouTube channel)
        # means every episode shows up twice and, on auto, gets transcribed
        # twice. Names differ slightly between the two ("... News" vs
        # "... News and Analysis"), so match on a normalized prefix and warn
        # rather than refuse — "The Daily" and "The Daily Show" are different.
        twin = next((s for s in load_store()["shows"] if _same_show_name(s["name"], name)), None)
        warning = (
            f"You already follow \u201c{twin['name']}\u201d as {twin['type']}. Following the same "
            "show twice gives you every episode twice \u2014 remove one with the \u00d7 in the list."
        ) if twin else None

        # parse_feed is a network call; keep it outside the lock. Take the
        # lock only for the read-modify-write, and re-read + re-check the
        # duplicate here against the fresh store — a concurrent add_show for
        # the same feed_url may have landed while the fetch above was in
        # flight.
        with _store_lock:
            data = load_store()
            if any(s["feed_url"] == feed_url for s in data["shows"]):
                raise ValueError("That show is already in your list.")

            # Seed `seen` with everything except the newest episode, so a fresh
            # subscription surfaces exactly one thing to try rather than a backlog.
            seen = [e["id"] for e in episodes[1:FEED_WINDOW]]
            show = {
                "id": f"s{int(datetime.now().timestamp() * 1000):x}",
                "name": name,
                "type": kind,
                "feed_url": feed_url,
                "source_url": url,
                "auto": False,
                "added_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "last_seen": episodes[1]["id"] if len(episodes) > 1 else None,
                "last_checked": None,
                "seen": seen,
                "folder": "unsorted",
            }
            data["shows"].append(show)
            save_store(data)
        out = {"id": show["id"], "name": name, "type": kind, "feed_url": feed_url,
               "auto": False, "added_at": show["added_at"], "folder": "unsorted"}
        if warning:
            out["warning"] = warning
        return out

    @bridge
    def remove_show(self, show_id: str) -> dict:
        with _store_lock:
            data = load_store()
            before = len(data["shows"])
            data["shows"] = [s for s in data["shows"] if s["id"] != show_id]
            if len(data["shows"]) == before:
                raise ValueError("That show isn't in your list.")
            save_store(data)
        # A removed show's queued/running work shouldn't keep burning CPU.
        for eid, st in self._worker.states().items():
            if st.get("show_id") == show_id and st.get("status") not in ("done", "failed", "cancelled"):
                self._worker.cancel(eid)
        return {"removed": show_id}

    @bridge
    def set_auto(self, show_id: str, auto: bool) -> dict:
        with _store_lock:
            data = load_store()
            show = _find_show(data, show_id)
            if not show:
                raise ValueError("That show isn't in your list.")
            show["auto"] = bool(auto)
            save_store(data)
            result = {"id": show_id, "auto": show["auto"]}
        return result

    @bridge
    def set_auto_train(self, show_id: str, auto_train: bool) -> dict:
        with _store_lock:
            data = load_store()
            show = _find_show(data, show_id)
            if not show:
                raise ValueError("That show isn't in your list.")
            show["auto_train"] = bool(auto_train)
            save_store(data)
            result = {"id": show_id, "auto_train": show["auto_train"]}
        return result

    # -- source folders -------------------------------------------------------

    @bridge
    def list_folders(self) -> list[dict]:
        return load_store()["folders"]

    @bridge
    def add_folder(self, name: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("Give the folder a name first.")
        with _store_lock:
            data = load_store()
            if any(f["name"].strip().lower() == name.lower() for f in data["folders"]):
                raise ValueError("A folder with that name already exists.")
            folder = {"id": f"f{int(datetime.now().timestamp() * 1000):x}", "name": name}
            data["folders"].append(folder)
            save_store(data)
        return folder

    @bridge
    def rename_folder(self, folder_id: str, name: str) -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("Give the folder a name first.")
        with _store_lock:
            data = load_store()
            folder = next((f for f in data["folders"] if f["id"] == folder_id), None)
            if not folder:
                raise ValueError("That folder doesn't exist.")
            if any(f["id"] != folder_id and f["name"].strip().lower() == name.lower()
                   for f in data["folders"]):
                raise ValueError("A folder with that name already exists.")
            folder["name"] = name  # "unsorted" may be renamed — its id never changes
            save_store(data)
        return folder

    @bridge
    def remove_folder(self, folder_id: str) -> dict:
        if folder_id == "unsorted":
            raise ValueError("The Unsorted folder can't be removed.")
        with _store_lock:
            data = load_store()
            before = len(data["folders"])
            data["folders"] = [f for f in data["folders"] if f["id"] != folder_id]
            if len(data["folders"]) == before:
                raise ValueError("That folder doesn't exist.")
            for show in data["shows"]:
                if show.get("folder") == folder_id:
                    show["folder"] = "unsorted"
            save_store(data)
        return {"removed": folder_id}

    @bridge
    def set_show_folder(self, show_id: str, folder_id: str) -> dict:
        with _store_lock:
            data = load_store()
            show = _find_show(data, show_id)
            if not show:
                raise ValueError("That show isn't in your list.")
            if not any(f["id"] == folder_id for f in data["folders"]):
                raise ValueError("That folder doesn't exist.")
            show["folder"] = folder_id
            save_store(data)
        return {"id": show_id, "folder": folder_id}

    # -- settings -------------------------------------------------------------

    @bridge
    def get_settings(self) -> dict:
        settings = load_store()["settings"]
        return {
            "model": settings.get("model", DEFAULT_SETTINGS["model"]),
            "lang": settings.get("lang", DEFAULT_SETTINGS["lang"]),
            "transcripts_dir": str(transcripts_dir()),
        }

    @bridge
    def set_settings(self, patch: dict) -> dict:
        if not isinstance(patch, dict):
            raise ValueError("Settings update must be an object.")
        # Only model/lang are user-settable here; transcripts_dir goes through
        # choose_folder (window) or set_transcripts_dir (CLI), and any other
        # key is a typo/future-flag we'd rather surface loudly than silently
        # swallow.
        unknown = set(patch) - {"model", "lang"}
        if unknown:
            raise ValueError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
        if "model" in patch and patch["model"] not in VALID_MODELS:
            raise ValueError(f"Unknown model: {patch['model']!r}")
        if "lang" in patch and patch["lang"] not in VALID_LANGS:
            raise ValueError(f"Unknown language: {patch['lang']!r}")
        with _store_lock:
            data = load_store()
            settings = data["settings"]
            # Validate the RESULTING combination, not just the patched field —
            # a patch may carry only one of the two keys, so check against
            # whatever the other one would end up being.
            merged_model = patch.get("model", settings.get("model", DEFAULT_SETTINGS["model"]))
            merged_lang = patch.get("lang", settings.get("lang", DEFAULT_SETTINGS["lang"]))
            if merged_lang == "ko" and merged_model.endswith(".en"):
                raise ValueError("Korean needs the large-v3 model — pick it under Model first.")
            if "model" in patch:
                settings["model"] = patch["model"]
            if "lang" in patch:
                settings["lang"] = patch["lang"]
            data["settings"] = settings
            save_store(data)
            result = {
                "model": settings.get("model", DEFAULT_SETTINGS["model"]),
                "lang": settings.get("lang", DEFAULT_SETTINGS["lang"]),
            }
        result["transcripts_dir"] = str(transcripts_dir())
        return result

    @bridge
    def set_transcripts_dir(self, path: str | None) -> dict:
        """Point transcripts at a folder without a dialog (the CLI's route).

        None or "" clears the override so transcripts go back to
        <SORI_HOME>/Transcripts. A path is expanded and created if missing;
        an existing non-directory is refused. Returns get_settings() data.
        """
        raw = (path or "").strip() if isinstance(path, str) else path
        if raw:
            target = Path(raw).expanduser()
            if target.exists() and not target.is_dir():
                raise ValueError(f"Not a folder: {target}")
            target.mkdir(parents=True, exist_ok=True)
            value: str | None = str(target.resolve())
        elif raw is None or raw == "":
            value = None
        else:
            raise ValueError("transcripts_dir must be a path or None.")
        with _store_lock:
            data = load_store()
            data["settings"]["transcripts_dir"] = value
            save_store(data)
        return self.get_settings()["data"]

    @bridge
    def get_training_settings(self) -> dict:
        import deck_render
        settings = load_store()["settings"]
        key = anthropic_api_key()
        return {
            "deck_theme": settings.get("deck_theme", DEFAULT_SETTINGS["deck_theme"]),
            "themes": deck_render.THEMES,
            "has_api_key": bool(key),
            "api_key_last4": key[-4:] if key else None,
        }

    @bridge
    def set_training_settings(self, patch: dict) -> dict:
        if not isinstance(patch, dict):
            raise ValueError("Settings update must be an object.")
        import deck_render
        unknown = set(patch) - {"deck_theme", "api_key"}
        if unknown:
            raise ValueError(f"Unknown setting(s): {', '.join(sorted(unknown))}")
        if "deck_theme" in patch and patch["deck_theme"] not in deck_render.THEMES:
            raise ValueError(f"Unknown deck theme: {patch['deck_theme']!r}")
        if "deck_theme" in patch:
            with _store_lock:
                data = load_store()
                data["settings"]["deck_theme"] = patch["deck_theme"]
                save_store(data)
        if "api_key" in patch:
            key = (patch["api_key"] or "").strip()
            creds = load_credentials()
            if key:
                creds["anthropic_api_key"] = key
            else:
                creds.pop("anthropic_api_key", None)  # empty string clears it
            save_credentials(creds)
        return self.get_training_settings()["data"]

    @bridge
    def choose_folder(self) -> dict:
        import webview
        res = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not res:
            return {"changed": False, "transcripts_dir": str(transcripts_dir())}
        old_dir = transcripts_dir()
        # Count what's about to be orphaned before we point the app elsewhere,
        # so the UI can warn instead of silently making old transcripts
        # unreachable from the picker.
        orphaned = sum(1 for _ in old_dir.rglob("*.txt"))
        with _store_lock:
            data = load_store()
            data["settings"]["transcripts_dir"] = str(res[0])
            save_store(data)
        return {"changed": True, "transcripts_dir": str(res[0]),
                "previous": str(old_dir), "orphaned": orphaned}

    @bridge
    def choose_files(self) -> dict:
        import webview
        res = self._window.create_file_dialog(
            webview.OPEN_DIALOG, allow_multiple=True,
            file_types=("Audio and video (*.mp3;*.m4a;*.wav;*.mp4)", "All files (*.*)"),
        )
        if not res:
            return {"queued": []}
        data = load_store()
        show = {"id": "imported", "name": "Imported"}
        today = datetime.now().strftime("%Y-%m-%d")
        queued = []
        for p in res:
            episode = {"id": p, "title": Path(p).stem, "url": p, "kind": "mp3", "date": today}
            self._worker.submit(show, episode, data["settings"],
                                priority=Worker.PRIORITY_MANUAL)
            queued.append(episode["id"])
        return {"queued": queued}

    # -- episodes -----------------------------------------------------------

    @bridge
    def check_shows(self) -> dict:
        return check_all()

    @bridge
    def transcribe_episode(self, show_id: str, episode: dict) -> dict:
        return self._queue_episode(show_id, episode)

    @bridge
    def retry_episode(self, show_id: str, episode: dict) -> dict:
        """Re-queue an episode by hand, wiping the automatic-retry budget."""
        return self._queue_episode(show_id, episode, reset=True)

    def _queue_episode(self, show_id: str, episode: dict, reset: bool = False) -> dict:
        data = load_store()
        show = _find_show(data, show_id)
        if not show:
            raise ValueError("That show isn't in your list.")
        if not isinstance(episode, dict) or not episode.get("url"):
            raise ValueError("That episode is missing its link.")
        episode.setdefault("id", episode["url"])
        if reset:
            _clear_failure(show_id, episode["id"])
        status = self._worker.submit(show, episode, data["settings"],
                                     priority=Worker.PRIORITY_MANUAL)
        return {"id": episode["id"], "status": status}

    @bridge
    def job_states(self) -> dict:
        return {"jobs": self._worker.states(), "pending": self._worker.pending()}

    @bridge
    def stop_episode(self, episode_id: str) -> dict:
        status = self._worker.cancel(episode_id)
        return {"id": episode_id, "status": status}

    @bridge
    def dismiss_episode(self, show_id: str, episode_id: str) -> dict:
        """Skip an episode for good: stop any job on it, drop its row, and mark
        it seen so neither the hourly poll nor "Check now" offers it again.
        Retry/Transcribe on the same episode later still works — a fresh
        submit clears the dismissal."""
        status = self._worker.dismiss(episode_id)
        _mark_seen(show_id, episode_id)
        return {"id": episode_id, "status": status}

    @bridge
    def dismiss_episodes(self, items: list) -> dict:
        """Bulk form of dismiss_episode: items = [{"show_id", "id"}, ...]. The
        UI passes what it is showing, so nothing here touches the network."""
        count = 0
        for item in items or []:
            if not isinstance(item, dict) or not item.get("show_id") or not item.get("id"):
                continue
            self._worker.dismiss(item["id"])
            _mark_seen(item["show_id"], item["id"])
            count += 1
        return {"dismissed": count}

    # -- training -------------------------------------------------------------

    @bridge
    def generate_training(self, transcript_path: str) -> dict:
        """Manual "Generate Training" trigger — everything it needs comes from
        the transcript file itself (+ its .json sidecar), so this works from
        the Library/Reader without needing the original show/episode objects
        still to be around (a show removed or a feed rewound doesn't matter)."""
        target = _confine_to_transcripts(transcript_path)
        data = _read_transcript_data(target)
        meta = data.get("meta", {})
        show_name = meta.get("show") or "Unsorted"
        episode = {"id": target.stem, "title": meta.get("title") or target.stem,
                   "date": meta.get("date", ""), "url": meta.get("url", "")}
        show = {"id": "t:" + _safe_name(show_name, 60), "name": show_name}
        status = self._trainer.submit(show, episode, target, load_store()["settings"])
        return {"id": episode["id"], "status": status}

    @bridge
    def train_job_states(self) -> dict:
        return {"jobs": self._trainer.states(), "pending": self._trainer.pending()}

    @bridge
    def stop_training(self, episode_id: str) -> dict:
        status = self._trainer.cancel(episode_id)
        return {"id": episode_id, "status": status}

    @bridge
    def list_trainings(self) -> list[dict]:
        return list_trainings()

    @bridge
    def open_training(self, path: str) -> dict:
        target = _confine_to_trainings(path)
        _open_in_explorer(target)
        return {"opened": str(target)}

    @bridge
    def open_trainings_folder(self) -> dict:
        _open_in_explorer(trainings_dir())
        return {"opened": str(trainings_dir())}

    # -- transcripts --------------------------------------------------------

    @bridge
    def list_transcripts(self) -> list[dict]:
        return list_transcripts()

    @bridge
    def open_transcript(self, path: str) -> dict:
        target = _confine_to_transcripts(path)
        _open_in_explorer(target)
        return {"opened": str(target)}

    @bridge
    def open_folder(self) -> dict:
        _open_in_explorer(transcripts_dir())
        return {"opened": str(transcripts_dir())}

    @bridge
    def read_transcript(self, path: str) -> dict:
        target = _confine_to_transcripts(path)
        return _read_transcript_data(target)

    @bridge
    def export_transcript(self, path: str, fmt: str) -> dict:
        if fmt not in ("md", "srt"):
            raise ValueError("Export format must be 'md' or 'srt'.")
        target = _confine_to_transcripts(path)
        data = _read_transcript_data(target)
        legacy = bool(data.get("legacy"))
        if fmt == "srt" and legacy:
            raise ValueError(
                "No timing data for this transcript — it predates timestamped "
                "transcripts. Delete the .txt and transcribe the episode again "
                "to get .srt export."
            )
        meta = data.get("meta", {})
        segments = data.get("segments", [])
        if fmt == "srt":
            written = target.with_suffix(".srt")
            written.write_text(_render_srt(segments), encoding="utf-8")
        else:
            written = target.with_suffix(".md")
            written.write_text(_render_md(meta, segments, legacy), encoding="utf-8")
        return {"path": str(written)}

    @bridge
    def search_transcripts(self, q: str) -> dict:
        q = (q or "").strip()
        if not q:
            raise ValueError("Type something to search for.")
        needle = q.lower()
        root = transcripts_dir()
        out: list[dict] = []
        scanned = 0
        for show_folder in sorted(root.iterdir()) if root.exists() else []:
            if not show_folder.is_dir():
                continue
            for f in sorted(show_folder.glob("*.txt"), reverse=True):
                if scanned >= 200:
                    # Cap hit — don't silently pretend this is the full result set.
                    return {"results": out, "truncated": True}
                scanned += 1
                try:
                    stat = f.stat()
                except OSError:
                    continue
                if stat.st_size > 5 * 1024 * 1024:
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                idx = text.lower().find(needle)
                if idx == -1:
                    continue
                start = max(0, idx - 60)
                end = min(len(text), idx + len(needle) + 60)
                snippet = text[start:end].replace("\n", " ").strip()
                if start > 0:
                    snippet = "…" + snippet
                if end < len(text):
                    snippet = snippet + "…"
                out.append({
                    "path": str(f), "show": show_folder.name, "title": f.stem,
                    "kb": round(stat.st_size / 1024, 1),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
                    "snippet": snippet,
                })
        return {"results": out, "truncated": False}

    @bridge
    def app_info(self) -> dict:
        return {
            "name": APP_NAME,
            "state_dir": str(state_dir()),
            "transcripts_dir": str(transcripts_dir()),
            "version": load_store().get("version", 2),
        }

    # -- background poller --------------------------------------------------

    def _start_poller(self, interval_seconds: int = 3600) -> None:
        def loop():
            while not self._stop.is_set():
                try:
                    result = check_all()
                    self._emit("checked", result)
                    self._auto_queue(result["episodes"])
                except Exception:
                    traceback.print_exc()
                self._stop.wait(interval_seconds)

        threading.Thread(target=loop, name="poller", daemon=True).start()

    def _auto_queue(self, episodes: list[dict]) -> None:
        data = load_store()
        settings = data["settings"]
        for ep in episodes:
            show = _find_show(data, ep["show_id"])
            if show and show.get("auto"):
                self._worker.submit(show, ep, settings)

    def _shutdown(self) -> None:
        self._stop.set()


def _open_in_explorer(target: Path) -> None:
    if hasattr(os, "startfile"):
        os.startfile(str(target))  # noqa: S606 - Windows shell open, no user input in argv
    else:  # pragma: no cover - dev convenience on non-Windows
        import subprocess
        subprocess.run(["xdg-open", str(target)], check=False)


# ---------------------------------------------------------------------------
# Shared operations (used by both the window and --sweep)
# ---------------------------------------------------------------------------

def check_all() -> dict:
    """Poll every show. Never raises — per-show failures come back as errors."""
    data = load_store()
    shows = data["shows"]
    found: list[dict] = []
    errors: list[dict] = []
    checked: set[str] = set()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Every show is an independent HTTP round-trip, so fetch them together;
    # results are collected in subscription order to keep output stable.
    if shows:
        with ThreadPoolExecutor(max_workers=min(FEED_WORKERS, len(shows))) as pool:
            pending = [(show, pool.submit(new_episodes_for, show)) for show in shows]
        for show, future in pending:
            try:
                found.extend(future.result())
                checked.add(show["id"])
            except Exception as exc:
                errors.append({"show_id": show["id"], "show": show["name"], "error": str(exc)})

    # Network calls above are slow, and the worker thread may have written a
    # `seen` marker while they ran. Re-read under the lock and touch only the
    # field this function owns, so a finished transcript is never clobbered.
    with _store_lock:
        fresh = load_store()
        for show in fresh["shows"]:
            if show["id"] in checked:
                show["last_checked"] = now
        save_store(fresh)

    found.sort(key=lambda e: e.get("date", ""), reverse=True)
    return {"episodes": found, "errors": errors, "checked_at": now,
            "show_count": len(data["shows"])}


def list_transcripts() -> list[dict]:
    out = []
    root = transcripts_dir()
    for show_folder in sorted(root.iterdir()) if root.exists() else []:
        if not show_folder.is_dir():
            continue
        for f in sorted(show_folder.glob("*.txt"), reverse=True):
            try:
                stat = f.stat()
            except OSError:
                continue
            out.append({
                "show": show_folder.name,
                "title": f.stem,
                "path": str(f),
                "kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
            })
    return out


def list_trainings() -> list[dict]:
    """One row per generated deck, pairing the .pptx with its .md study guide
    when both exist (they're written together by run_training)."""
    out = []
    root = trainings_dir()
    for show_folder in sorted(root.iterdir()) if root.exists() else []:
        if not show_folder.is_dir():
            continue
        for f in sorted(show_folder.glob("*.pptx"), reverse=True):
            try:
                stat = f.stat()
            except OSError:
                continue
            md = f.with_suffix(".md")
            out.append({
                "show": show_folder.name,
                "title": f.stem,
                "pptx_path": str(f),
                "md_path": str(md) if md.exists() else None,
                "kb": round(stat.st_size / 1024, 1),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
            })
    return out


# ---------------------------------------------------------------------------
# Headless sweep
# ---------------------------------------------------------------------------

def sweep() -> int:
    """Check every show, transcribe new episodes for auto shows, report, exit."""
    log_path = state_dir() / "sweep.log"
    lines: list[str] = []

    def say(msg: str) -> None:
        lines.append(msg)
        # A windowed EXE has no console; the log file is the real output there.
        try:
            print(msg)
        except Exception:
            pass

    started = datetime.now()
    say(f"=== {APP_NAME} sweep — {started.strftime('%Y-%m-%d %H:%M:%S')} ===")

    data = load_store()
    if not data["shows"]:
        say(f"No shows subscribed yet. Open {APP_NAME} and add one.")
        _append_log(log_path, lines)
        return 0

    result = check_all()
    say(f"Checked {result['show_count']} show(s): {len(result['episodes'])} new episode(s).")
    for err in result["errors"]:
        say(f"  ! {err['show']}: {err['error']}")

    auto_ids = {s["id"] for s in data["shows"] if s.get("auto")}
    todo = [e for e in result["episodes"] if e["show_id"] in auto_ids]
    skipped = len(result["episodes"]) - len(todo)

    for ep in result["episodes"]:
        flag = "auto" if ep["show_id"] in auto_ids else "manual"
        say(f"  - [{flag}] {ep['show_name']}: {ep['date']} {ep['title']}")

    if skipped:
        say(f"{skipped} episode(s) left for manual review (show not set to auto).")

    # check_all() rewrote the store (last_checked); re-read so `seen` and the
    # failure counters below are the current ones, not a pre-network snapshot.
    data = load_store()

    auto_train_ids = {s["id"] for s in data["shows"] if s.get("auto_train")}
    done = failed = trained = train_failed = 0
    for ep in todo:
        show = _find_show(data, ep["show_id"])
        if not show:
            continue
        say(f"  > transcribing: {ep['title']}")
        noted = set()

        def note(stage: str, _frac=None, _seen=noted) -> None:
            if stage == "downloading model" and stage not in _seen:
                _seen.add(stage)
                say("    downloading the Whisper model (first run only)…")

        try:
            path = run_transcription(show, ep, data["settings"], on_progress=note)
            _mark_seen(show["id"], ep["id"])
            done += 1
            say(f"    saved: {path}")
        except Exception as exc:
            message = str(exc) if isinstance(exc, TranscriptionError) else f"unexpected error: {exc}"
            attempts = _record_failure(show["id"], ep["id"], message)
            left = max(MAX_ATTEMPTS - attempts, 0)
            failed += 1
            tail = (f" (will try again next sweep, {left} left)" if left
                    else " (giving up — use Retry in the app)")
            say(f"    failed: {message}{tail}")
            continue

        if show["id"] in auto_train_ids:
            say(f"  > generating training: {ep['title']}")
            try:
                pptx_path, md_path = run_training(show, ep, path, data["settings"])
                trained += 1
                say(f"    saved: {pptx_path}")
            except Exception as exc:
                message = str(exc) if isinstance(exc, TrainingError) else f"unexpected error: {exc}"
                train_failed += 1
                say(f"    training failed: {message}")

    elapsed = (datetime.now() - started).total_seconds()
    say(f"Done in {elapsed:.1f}s — {done} transcribed, {failed} failed, {skipped} skipped, "
        f"{trained} trained, {train_failed} training failed.")
    _append_log(log_path, lines)
    return 0


def selftest() -> int:
    """Import every backend and report. Proves a packaged build is complete.

    The packaged app has no console, so this writes to sweep.log too — it is
    the one command to run when something "doesn't work" on another machine.
    """
    lines = [f"=== {APP_NAME} self-test — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ==="]
    lines.append(f"frozen: {bool(getattr(sys, 'frozen', False))}  python: {sys.version.split()[0]}")
    lines.append(f"state dir: {state_dir()}")
    lines.append(f"ui: {app_dir() / 'ui' / 'index.html'} "
                 f"({'found' if (app_dir() / 'ui' / 'index.html').exists() else 'MISSING'})")

    checks = [
        ("yt_dlp", "YouTube captions"),
        ("faster_whisper", "local transcription"),
        ("ctranslate2", "whisper runtime"),
        ("av", "audio decoding"),
        ("onnxruntime", "voice-activity filter"),
        ("webview", "app window"),
        ("anthropic", "training generation (needs an API key too)"),
        ("pptx", "deck rendering (python-pptx)"),
    ]
    failures = 0
    for module, what in checks:
        try:
            mod = __import__(module)
            version = getattr(mod, "__version__", "?")
            lines.append(f"  ok    {module:<16} {version:<12} ({what})")
        except Exception as exc:
            failures += 1
            lines.append(f"  FAIL  {module:<16} {'':<12} ({what}) — {exc}")

    # Not third-party packages, so not in `checks` above: prove the app's own
    # new modules import cleanly in a frozen build too, and that the vendored
    # bundled font assets actually landed where PyInstaller was told to put
    # them (Sori.spec datas) — a missing/misnamed data entry wouldn't show up
    # as an import failure otherwise. The fonts are OFL and ship in every
    # checkout; only engine/ is optional.
    # The private BH engine is optional (see themes/README.md): a checkout
    # without engine/ renders with themes/studio and is fully functional, so
    # its absence is reported, never counted as a failure.
    try:
        import deck_render
        themes = ", ".join(deck_render.THEMES)
        if deck_render.deckgen is not None:
            n = (len(list(deck_render.install_fonts.FONTS_DIR.glob("*.ttf")))
                 if deck_render.install_fonts is not None else 0)
            detail = f"engine present, {n} font(s) bundled, themes: {themes}"
        else:
            detail = f"no engine, themes: {themes}"
        lines.append(f"  ok    deck_render      {'':<12} (training deck rendering, {detail})")
    except Exception as exc:
        failures += 1
        lines.append(f"  FAIL  deck_render      {'':<12} (training deck rendering) — {exc}")

    lines.append("All backends present." if not failures else f"{failures} backend(s) missing.")
    for line in lines:
        try:
            print(line)
        except Exception:
            pass
    _append_log(state_dir() / "sweep.log", lines)
    return 1 if failures else 0


def _append_log(path: Path, lines: list[str]) -> None:
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

def run_window() -> int:
    import webview

    index = app_dir() / "ui" / "index.html"
    if not index.exists():
        print(f"UI not found at {index}", file=sys.stderr)
        return 1

    api = Api()
    window = webview.create_window(
        APP_NAME,
        str(index),
        js_api=api,
        # The page lays out at 1024 logical px minimum (ui/index.html). On a
        # 125% or 150% display a 1100 px window is narrower than that and the
        # right-hand buttons are cut off until the user resizes; 1360x820 is
        # still comfortable on a 1080p screen at 100%.
        width=1360,
        height=820,
        min_size=(900, 600),
        background_color="#F7F7F4",
    )
    api._attach(window)

    def on_start():
        api._worker.start()
        api._trainer.start()
        api._start_poller(3600)

    webview.start(on_start, debug=bool(os.environ.get("SORI_DEBUG")
                                        or os.environ.get("PODCAST_STUDIO_DEBUG")))
    api._shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="app.py", description=f"{APP_NAME} — desktop app for podcast-transcriber."
    )
    parser.add_argument(
        "--sweep", action="store_true",
        help="Headless: check every show, transcribe new episodes for auto shows, exit.",
    )
    parser.add_argument(
        "--selftest", action="store_true",
        help="Check that every transcription backend imports, then exit.",
    )
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    return sweep() if args.sweep else run_window()


if __name__ == "__main__":
    sys.exit(main())
