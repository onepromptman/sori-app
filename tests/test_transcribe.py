"""transcribe.py CLI: the saved-transcript header matches what the sweep
writes (so train.py reads it back), feed dates parse, --title/--show/--date
override the source. No network: the feed fetch is monkeypatched.
"""

from __future__ import annotations

import argparse

import pytest

import train
import transcribe as tx


def test_header_block_round_trips_through_train():
    meta = {"title": "Some Episode", "show": "The Daily", "date": "2026-08-31", "url": "https://x/ep.mp3"}
    text = tx.header_block(meta) + "body"
    assert text == "Some Episode\nThe Daily — 2026-08-31\nhttps://x/ep.mp3\n\nbody"
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
    assert out.read_text(encoding="utf-8") == "T\nS — 2026-01-02\nu\n\nbody"
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
