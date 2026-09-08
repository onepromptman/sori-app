"""shows.py: subscriptions and folders from the CLI, same store as the window.

Every test calls ``shows.main(argv)`` in-process (never a subprocess) under
the ``sori_home`` fixture, with ``parse_feed`` replaced by ``fake_feed`` so no
test touches the network. The stdout/stderr contract is asserted through
``capsys``.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def shows(app_mod):
    import shows
    return shows


def _run(shows, capsys, argv):
    code = shows.main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def _added(shows, capsys, url, *flags):
    code, out, _ = _run(shows, capsys, ["add", url, "--json", *flags])
    assert code == 0, out
    return json.loads(out)


# -- list / add / remove --------------------------------------------------------

def test_list_empty(shows, capsys):
    code, out, err = _run(shows, capsys, ["list"])
    assert code == 0
    assert "no shows yet" in out
    code, out, _ = _run(shows, capsys, ["list", "--json"])
    assert code == 0 and json.loads(out) == []


def test_add_then_list_and_remove_by_id(shows, fake_feed, capsys):
    fake_feed("Fake Show")
    show = _added(shows, capsys, "https://x/feed")
    assert show["name"] == "Fake Show" and show["type"] == "rss"
    assert show["auto"] is False

    code, out, _ = _run(shows, capsys, ["list"])
    assert code == 0
    header, row = out.splitlines()[:2]
    assert header.split()[:3] == ["id", "name", "type"]
    assert show["id"] in row and "Fake Show" in row and "Unsorted" in row

    code, out, _ = _run(shows, capsys, ["remove", show["id"]])
    assert code == 0 and show["id"] in out
    code, out, _ = _run(shows, capsys, ["list", "--json"])
    assert json.loads(out) == []


def test_add_with_flags_sets_auto_auto_train_and_folder(shows, fake_feed, capsys):
    fake_feed("Fake Show")
    assert _run(shows, capsys, ["folder", "add", "AI"])[0] == 0
    show = _added(shows, capsys, "https://x/feed", "--auto", "--auto-train", "--folder", "ai")
    assert show["auto"] is True and show["auto_train"] is True
    assert show["folder"].startswith("f")
    rows = json.loads(_run(shows, capsys, ["list", "--json"])[1])
    assert rows[0]["auto"] and rows[0]["auto_train"] and rows[0]["folder"] == show["folder"]


def test_add_unknown_folder_fails_before_fetching(shows, app_mod, monkeypatch, capsys):
    # bridge() would turn any exception from a fetch into a plain exit 1, so
    # count calls and check the message instead of relying on the raise.
    calls: list[tuple] = []

    def boom(*a, **k):
        calls.append(a)
        raise AssertionError("feed must not be fetched")
    monkeypatch.setattr(app_mod, "parse_feed", boom)
    code, out, err = _run(shows, capsys, ["add", "https://x/feed", "--folder", "nope"])
    assert code == 1 and out == ""
    assert err.startswith("!! no folder matches 'nope'"), err
    assert calls == [], "the feed was fetched before the folder was resolved"
    assert json.loads(_run(shows, capsys, ["list", "--json"])[1]) == []


def test_json_output_is_valid_for_a_non_bmp_name(shows, fake_feed, capsys):
    # An emoji in a channel title must survive --json on a cp1252 console: the
    # CLIs escape with backslashreplace, which would emit \\U0001f600 (not JSON).
    # json.dumps with ensure_ascii on does the escaping itself, as a surrogate pair.
    name = "Show \U0001f600 Daily"
    fake_feed(name)
    show = _added(shows, capsys, "https://x/feed")
    assert show["name"] == name
    code, out, _ = _run(shows, capsys, ["list", "--json"])
    assert code == 0 and out.isascii()
    assert json.loads(out)[0]["name"] == name


def test_add_bad_link_is_exit_1(shows, fake_feed, capsys):
    code, out, err = _run(shows, capsys, ["add", "not a link"])
    assert code == 1 and out == "" and err.startswith("!! ")


def test_add_duplicate_feed_is_exit_1(shows, fake_feed, capsys):
    _added(shows, capsys, "https://x/feed")
    code, _, err = _run(shows, capsys, ["add", "https://x/feed"])
    assert code == 1 and "already" in err


def test_twin_warning_goes_to_stderr_not_failure(shows, fake_feed, capsys):
    fake_feed("The Fake Show: News")
    _added(shows, capsys, "https://x/one")
    fake_feed("The Fake Show: News and Analysis")
    code, out, err = _run(shows, capsys, ["add", "https://x/two"])
    assert code == 0
    assert out.startswith("added ")
    assert err.startswith("warning:") and "already follow" in err


def test_remove_by_name_case_insensitive(shows, fake_feed, capsys):
    fake_feed("Fake Show")
    _added(shows, capsys, "https://x/feed")
    code, out, _ = _run(shows, capsys, ["remove", "fake show"])
    assert code == 0 and out.startswith("removed ")


def test_ambiguous_name_is_exit_1_and_id_still_works(shows, fake_feed, capsys):
    fake_feed("Same Name")
    a = _added(shows, capsys, "https://x/one")
    b = _added(shows, capsys, "https://x/two")
    code, out, err = _run(shows, capsys, ["remove", "Same Name"])
    assert code == 1 and out == ""
    assert err.startswith("!! ") and a["id"] in err and b["id"] in err
    assert _run(shows, capsys, ["remove", a["id"]])[0] == 0
    # Only one left now, so the name resolves again.
    assert _run(shows, capsys, ["remove", "same name"])[0] == 0
    assert json.loads(_run(shows, capsys, ["list", "--json"])[1]) == []


def test_unknown_show_is_exit_1(shows, capsys):
    code, out, err = _run(shows, capsys, ["remove", "s404"])
    assert code == 1 and out == "" and err.startswith("!! ")
    assert "Traceback" not in err


# -- auto / auto-train -------------------------------------------------------------

def test_auto_and_auto_train_toggle(shows, fake_feed, capsys):
    fake_feed("Fake Show")
    sid = _added(shows, capsys, "https://x/feed")["id"]
    for verb, key in (("auto", "auto"), ("auto-train", "auto_train")):
        code, out, _ = _run(shows, capsys, [verb, "Fake Show", "on"])
        assert code == 0 and out.strip() == f"{sid} {verb} on"
        assert json.loads(_run(shows, capsys, ["list", "--json"])[1])[0][key] is True
        code, out, _ = _run(shows, capsys, [verb, sid, "off"])
        assert code == 0 and out.strip() == f"{sid} {verb} off"
        assert json.loads(_run(shows, capsys, ["list", "--json"])[1])[0][key] is False


def test_auto_bad_state_is_usage_error(shows, capsys):
    assert _run(shows, capsys, ["auto", "s1", "maybe"])[0] == 2


# -- folders -----------------------------------------------------------------------

def test_folder_lifecycle_and_set(shows, fake_feed, capsys):
    fake_feed("Fake Show")
    sid = _added(shows, capsys, "https://x/feed")["id"]

    code, out, _ = _run(shows, capsys, ["folder", "add", "Research"])
    assert code == 0 and out.startswith("added folder ")
    fid = out.split()[2]

    code, out, _ = _run(shows, capsys, ["folder", "list"])
    assert code == 0 and "Unsorted" in out and "Research" in out

    code, out, _ = _run(shows, capsys, ["folder", "set", "fake show", "research"])
    assert code == 0 and out.strip() == f"{sid} -> folder {fid}"
    assert json.loads(_run(shows, capsys, ["list", "--json"])[1])[0]["folder"] == fid
    assert "Research" in _run(shows, capsys, ["list"])[1]

    code, out, _ = _run(shows, capsys, ["folder", "rename", "Research", "Papers"])
    assert code == 0 and out.strip() == f"renamed {fid} to Papers"

    code, out, _ = _run(shows, capsys, ["folder", "remove", "papers"])
    assert code == 0
    assert json.loads(_run(shows, capsys, ["list", "--json"])[1])[0]["folder"] == "unsorted"


def test_folder_errors_are_exit_1(shows, capsys):
    assert _run(shows, capsys, ["folder", "remove", "unsorted"])[0] == 1
    assert _run(shows, capsys, ["folder", "remove", "nope"])[0] == 1
    assert _run(shows, capsys, ["folder", "add", "Unsorted"])[0] == 1
    assert _run(shows, capsys, ["folder", "set", "s404", "unsorted"])[0] == 1


# -- check -------------------------------------------------------------------------

def test_check_lists_new_episodes(shows, fake_feed, seeded_show, capsys):
    code, out, err = _run(shows, capsys, ["check"])
    assert code == 0
    assert "1 show(s), 7 new episode(s)" in out
    assert "Fake Show" in out and "Episode 7" in out
    code, out, _ = _run(shows, capsys, ["check", "--json"])
    data = json.loads(out)
    assert data["show_count"] == 1 and len(data["episodes"]) == 7 and data["errors"] == []


# -- usage / parity ----------------------------------------------------------------

def test_usage_errors_are_exit_2(shows, capsys):
    assert _run(shows, capsys, [])[0] == 2
    assert _run(shows, capsys, ["bogus"])[0] == 2
    assert _run(shows, capsys, ["add"])[0] == 2
    assert _run(shows, capsys, ["folder"])[0] == 2
    assert _run(shows, capsys, ["--help"])[0] == 0


def test_store_parity_with_api(shows, app_mod, fake_feed, capsys):
    """What the CLI wrote is what the window reads, and vice versa."""
    fake_feed("From CLI")
    cli = _added(shows, capsys, "https://x/cli", "--auto")
    api = app_mod.Api()
    seen = api.list_shows()["data"]
    assert [s["id"] for s in seen] == [cli["id"]]
    assert seen[0]["auto"] is True and seen[0]["name"] == "From CLI"

    fake_feed("From Window")
    win = api.add_show("https://x/window")["data"]
    rows = json.loads(_run(shows, capsys, ["list", "--json"])[1])
    assert [r["id"] for r in rows] == [cli["id"], win["id"]]
    assert rows[1]["name"] == "From Window"

    assert _run(shows, capsys, ["remove", win["id"]])[0] == 0
    assert [s["id"] for s in api.list_shows()["data"]] == [cli["id"]]


# -- handoff 1.2 DoD: subscribe from the CLI, then the sweep picks it up ---------

def test_cli_added_show_is_swept(shows, app_mod, fake_feed, fake_transcriber, capsys):
    fake_transcriber.seconds = 0.1
    _added(shows, capsys, "https://x/feed", "--auto")
    assert app_mod.sweep() == 0
    # add_show seeds `seen` with all but the newest episode, so exactly one lands.
    assert fake_transcriber.made == ["e1"]
    assert (app_mod.transcripts_dir() / "Fake Show" / "e1.txt").exists()
