from pathlib import Path

import pytest


def test_open_sample_adds_a_readable_library_item_without_overwriting_it(app_mod):
    api = app_mod.Api()
    result = api.open_sample()
    assert result["ok"]
    target = Path(result["data"])
    assert api.read_transcript(str(target))["data"]["meta"]["title"].startswith("DEMO")
    assert any(item["path"] == str(target) for item in api.list_transcripts()["data"])
    target.write_text("My sample edits", encoding="utf-8")
    assert api.open_sample() == result
    assert target.read_text(encoding="utf-8") == "My sample edits"


@pytest.mark.parametrize("cached, available", [(False, True), (True, True), (False, False)])
def test_speech_setup_reuses_the_cache_and_reports_download_failure(app_mod, monkeypatch, tmp_path, cached, available):
    from faster_whisper import utils
    from huggingface_hub.errors import LocalEntryNotFoundError

    for name in ("config.json", "model.bin", "tokenizer.json"):
        (tmp_path / name).touch()
    api = app_mod.Api()
    real_downloads = []

    def download(model, *, local_files_only=False, use_auth_token=None):
        assert model == "base.en"
        assert use_auth_token is False
        if local_files_only:
            if not cached:
                raise LocalEntryNotFoundError("empty cache")
        else:
            real_downloads.append(model)
            if not available:
                raise OSError("offline")
        return str(tmp_path)

    class ImmediateThread:
        def __init__(self, *, target, **_):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(app_mod.tx, "whisper_backend", lambda device: "faster")
    monkeypatch.setattr(utils, "download_model", download)
    monkeypatch.setattr(app_mod.threading, "Thread", ImmediateThread)
    api._start_speech_setup()
    assert api.speech_setup()["data"] == ("ready" if available else "deferred")
    assert real_downloads == ([] if cached else ["base.en"])


def test_caption_rate_limit_recommends_the_podcast_feed(app_mod, monkeypatch):
    def reject_captions(*_):
        raise RuntimeError("Unable to download subtitles for 'en': HTTP Error 429: Too Many Requests")

    monkeypatch.setattr(app_mod.tx, "fetch_youtube_caption_segments", reject_captions)
    show = {"name": "Example show"}
    episode = {"id": "ep", "title": "An episode", "kind": "youtube", "url": "https://example.test/watch"}
    with pytest.raises(app_mod.TranscriptionError, match="podcast RSS feed"):
        app_mod.run_transcription(show, episode, {})
