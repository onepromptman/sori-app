"""transcribe.py CLI: the saved-transcript header matches what the sweep
writes (so train.py reads it back), feed dates parse, --title/--show/--date
override the source. No network: the feed fetch is monkeypatched.
"""

from __future__ import annotations

import argparse
import sys

import pytest

import train
import transcribe as tx


def test_header_block_round_trips_through_train():
    meta = {"title": "Some Episode", "show": "The Daily", "date": "2026-08-31", "url": "https://x/ep.mp3"}
    text = tx.header_block(meta) + "body"
    assert text == "Some Episode\nThe Daily \u2014 2026-08-31\nhttps://x/ep.mp3\n\nbody"
    assert train._header_meta(text) == {"title": "Some Episode", "show": "The Daily", "date": "2026-08-31"}


def test_header_block_is_empty_without_a_title():
    assert tx.header_block(None) == ""
    assert tx.header_block({"url": "https://x", "title": "  "}) == ""


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Mon, 31 Aug 2026 09:50:02 +0000", "2026-08-31"),
        ("20260831", "2026-08-31"),
        ("2026-08-31", "2026-08-31"),
        ("", ""),
        ("not a date", ""),
    ],
)
def test_iso_date(raw, expected):
    assert tx._iso_date(raw) == expected


def test_write_output_prepends_header_only_when_saving(tmp_path, capsys):
    out = tmp_path / "t.txt"
    tx._write_output("body", str(out), {"title": "T", "show": "S", "date": "2026-01-02", "url": "u"})
    assert out.read_text(encoding="utf-8") == "T\nS \u2014 2026-01-02\nu\n\nbody"
    capsys.readouterr()
    tx._write_output("body", None, {"title": "T"})
    assert capsys.readouterr().out.strip() == "body"


def test_meta_from_args_overrides_source():
    args = argparse.Namespace(title="Mine", show=None, date="2026-02-03")
    assert tx._meta_from_args(args, {"title": "Theirs", "show": "S", "url": "u"}) == {
        "title": "Mine",
        "show": "S",
        "date": "2026-02-03",
        "url": "u",
    }


def test_parser_accepts_header_flags_on_every_transcribing_verb():
    p = tx.build_parser()
    a = p.parse_args(["episode", "https://f", "words", "--title", "T", "--show", "S", "--date", "2026-01-01"])
    assert (a.title, a.show, a.date) == ("T", "S", "2026-01-01")
    assert p.parse_args(["youtube", "https://y", "--show", "S"]).show == "S"
    assert p.parse_args(["audio", "x.mp3", "--title", "T"]).title == "T"


def test_parse_feed_with_title(monkeypatch):
    xml = (
        b"<rss><channel><title>The Daily</title><item><title>Ep</title>"
        b"<enclosure url='https://x/1.mp3'/>"
        b"<pubDate>Mon, 31 Aug 2026 09:50:02 +0000</pubDate></item></channel></rss>"
    )
    monkeypatch.setattr(tx, "fetch_xml", lambda url, timeout=30: xml)
    show, eps = tx._parse_feed_with_title("https://feed")
    assert show == "The Daily"
    assert eps[0]["title"] == "Ep" and eps[0]["mp3_url"] == "https://x/1.mp3"
    assert tx._iso_date(eps[0]["pub_date"]) == "2026-08-31"


def test_same_title_and_date_do_not_reuse_another_episode(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod.tx, "fetch_youtube_caption_segments", lambda url, lang: [{"text": url}])
    show = {"id": "show", "name": "Fictional"}
    first = {
        "id": "one",
        "title": "Same",
        "date": "2026-01-01",
        "url": "https://example.com/one",
        "kind": "youtube",
    }
    second = {**first, "id": "two", "url": "https://example.com/two"}
    a = app_mod.run_transcription(show, first, {})
    b = app_mod.run_transcription(show, second, {})
    assert a != b
    assert "https://example.com/one" in a.read_text(encoding="utf-8")
    assert "https://example.com/two" in b.read_text(encoding="utf-8")
    assert app_mod.run_transcription(show, first, {}) == a
    assert app_mod.run_transcription(show, second, {}) == b


def test_episode_date_cannot_create_nested_output_path(app_mod):
    episode = {"id": "one", "title": "Fictional", "date": "../../escape", "url": "https://example.com/one"}
    result = app_mod.transcript_path_for("Fictional", episode)
    assert result.parent == app_mod.transcripts_dir() / "Fictional"


def test_rolling_captions_keep_longest_line():
    import transcribe

    vtt = "WEBVTT\n\n00:00.000 --> 00:01.000\nHello\n\n00:01.000 --> 00:02.000\nHello world\n"
    assert transcribe._clean_vtt(vtt) == "Hello world"


def test_an_unreachable_feed_is_one_plain_line(monkeypatch, capsys):
    """Regression: `list` on a dead feed printed a Python traceback."""
    import urllib.error

    def dead(url, timeout=30):
        raise urllib.error.URLError("[Errno 11001] getaddrinfo failed")

    monkeypatch.setattr(tx, "fetch_xml", dead)
    monkeypatch.setattr(sys, "argv", ["transcribe.py", "list", "https://feeds.example.test/show?token=abc"])
    with pytest.raises(SystemExit) as stop:
        tx.main()
    message = str(stop.value.code)
    assert message.startswith("!! couldn't reach the server")
    assert "\n" not in message and "Traceback" not in message and "token" not in message


def test_a_page_that_is_not_a_feed_is_one_plain_line(monkeypatch):
    monkeypatch.setattr(tx, "fetch_xml", lambda url, timeout=30: b"<html><p>not a feed")
    monkeypatch.setattr(sys, "argv", ["transcribe.py", "list", "https://example.test/"])
    with pytest.raises(SystemExit) as stop:
        tx.main()
    assert str(stop.value.code).startswith("!! that address did not return a podcast feed")


def test_the_audio_verb_writes_a_header(monkeypatch, tmp_path):
    """Regression: `audio` saved bare text, so train.py had no title to read."""
    monkeypatch.setattr(tx, "_whisper_or_exit", lambda path, model, device: ("hello there", 6.0))
    out = tmp_path / "t.txt"
    audio = tmp_path / "Marlow Creek update.mp3"
    audio.write_bytes(b"")
    monkeypatch.setattr(
        sys, "argv", ["transcribe.py", "audio", str(audio), "--out", str(out), "--show", "Town Hall"]
    )
    tx.main()
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Marlow Creek update"
    assert lines[2] == "Marlow Creek update.mp3"
    assert lines[1].startswith("Town Hall")
    assert lines[-1] == "hello there"


def test_an_unexpected_failure_does_not_echo_a_full_url(monkeypatch):
    def boom(url, timeout=30):
        raise RuntimeError("ERROR: unable to download https://cdn.example.test/ep.mp3?token=abc123")

    monkeypatch.setattr(tx, "fetch_xml", boom)
    monkeypatch.setattr(sys, "argv", ["transcribe.py", "list", "https://example.test/feed"])
    with pytest.raises(SystemExit) as stop:
        tx.main()
    assert "cdn.example.test" in str(stop.value.code) and "abc123" not in str(stop.value.code)


def test_source_title_comes_from_the_file_name():
    assert tx._source_title("https://cdn.example.test/eps/Ep%2012.mp3?sig=abc") == "Ep 12"
    assert tx._source_title("C:/audio/standup.wav") == "standup"
