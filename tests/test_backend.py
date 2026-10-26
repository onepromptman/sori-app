"""Local Whisper backend selection and the MLX path, without MLX installed.

A fake `mlx_whisper` module stands in for the real one (Apple-only), so this
runs on every CI OS. Nothing here touches faster-whisper either: the point of
the MLX branch is that it never imports it.
"""
from __future__ import annotations

import sys
import threading
import types
from pathlib import Path

import pytest

import transcribe as tx


@pytest.fixture
def fake_mlx(monkeypatch):
    calls: dict = {}
    mod = types.ModuleType("mlx_whisper")
    loader = types.ModuleType("mlx_whisper.load_models")

    def load_model(repo):
        calls["loaded"] = repo
        return object()

    def transcribe(path, **kwargs):
        calls["transcribe"] = (path, kwargs)
        return {"segments": [
            {"start": 0.0, "end": 2.5, "text": " Hello there. "},
            {"start": 2.5, "end": 5.0, "text": ""},
            {"start": 5.0, "end": 9.0, "text": "Second segment."},
        ]}

    loader.load_model = load_model
    mod.load_models = loader
    mod.transcribe = transcribe
    monkeypatch.setitem(sys.modules, "mlx_whisper", mod)
    monkeypatch.setitem(sys.modules, "mlx_whisper.load_models", loader)
    monkeypatch.setitem(sys.modules, "faster_whisper", None)  # import would raise
    monkeypatch.setenv("SORI_WHISPER_BACKEND", "mlx")
    tx._MODEL_CACHE.clear()
    yield calls
    tx._MODEL_CACHE.clear()


def test_backend_override_and_cuda(monkeypatch):
    monkeypatch.setenv("SORI_WHISPER_BACKEND", "mlx")
    assert tx.whisper_backend("cpu") == "mlx"
    assert tx.whisper_backend("cuda") == "faster"     # MLX has no CUDA
    monkeypatch.setenv("SORI_WHISPER_BACKEND", "faster")
    assert tx.whisper_backend("cpu") == "faster"
    monkeypatch.setenv("SORI_WHISPER_BACKEND", "nonsense")
    monkeypatch.setattr(sys, "platform", "linux")
    assert tx.whisper_backend("cpu") == "faster"


def test_backend_auto_on_apple_silicon_only_when_installed(monkeypatch):
    monkeypatch.delenv("SORI_WHISPER_BACKEND", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(tx.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(tx.importlib.util, "find_spec", lambda name: None)
    assert tx.whisper_backend() == "faster"
    monkeypatch.setattr(tx.importlib.util, "find_spec", lambda name: object())
    assert tx.whisper_backend() == "mlx"
    monkeypatch.setattr(tx.platform, "machine", lambda: "x86_64")
    assert tx.whisper_backend() == "faster"


def test_mlx_repo_mapping():
    assert tx.mlx_repo("base.en") == "mlx-community/whisper-base.en-mlx"
    assert tx.mlx_repo("large-v3") == "mlx-community/whisper-large-v3-mlx"
    assert tx.mlx_repo("medium.en") == "mlx-community/whisper-medium.en-mlx"
    assert tx.mlx_repo("someone/custom-repo") == "someone/custom-repo"


def test_mlx_segments_same_shape(fake_mlx, tmp_path):
    progress = []
    segs, duration = tx._transcribe_whisper_segments(
        tmp_path / "x.mp3", "base.en", "cpu", on_progress=progress.append, language=None)
    assert fake_mlx["loaded"] == "mlx-community/whisper-base.en-mlx"
    path, kwargs = fake_mlx["transcribe"]
    assert kwargs["path_or_hf_repo"] == "mlx-community/whisper-base.en-mlx"
    assert "language" not in kwargs
    assert segs == [{"start": 0.0, "end": 2.5, "text": "Hello there."},
                    {"start": 5.0, "end": 9.0, "text": "Second segment."}]
    assert duration == 9.0
    assert progress and progress[-1] == 1.0
    # and the plain-text wrapper the CLI uses still works through it
    text, dur = tx._transcribe_whisper(tmp_path / "x.mp3", "base.en", "cpu")
    assert text == "Hello there. Second segment."


def test_mlx_language_and_cancel(fake_mlx, tmp_path):
    segs, _ = tx._transcribe_whisper_segments(tmp_path / "x.mp3", "large-v3", "cpu", language="ko")
    assert fake_mlx["transcribe"][1]["language"] == "ko"
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(tx.TranscriptionCancelled):
        tx._transcribe_whisper_segments(tmp_path / "x.mp3", "large-v3", "cpu", cancel=cancel)


def test_model_cache_check_knows_mlx_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    assert not tx.whisper_model_is_cached("base.en")
    (tmp_path / "models--mlx-community--whisper-base.en-mlx").mkdir()
    assert tx.whisper_model_is_cached("base.en")
    assert Path(tmp_path).exists()
