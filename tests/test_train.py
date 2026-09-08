"""train.py: header parsing, key lookup order, exit codes, and the spend guard.

No test here can bill: ``training.generate_training`` is stubbed wherever a
key is present, and the one test that leaves it live proves that conftest's
fake ``anthropic`` module refuses to build a client. Keys in this file are
made up and are never echoed in an assertion message (last 4 chars at most).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import deck_render
import train
import training as tr

HEADER_EMDASH = "Some Episode\nThe Daily — 2026-09-04\nhttps://example.test/ep\n\nbody text\n"
HEADER_HYPHEN = "Some Episode\nThe Daily - 2026-09-04\nhttps://example.test/ep\n\nbody text\n"
NO_HEADER = "just a transcript with no header at all"


# ---- header parsing --------------------------------------------------------

@pytest.mark.parametrize("text", [HEADER_EMDASH, HEADER_HYPHEN], ids=["emdash", "hyphen"])
def test_header_meta_reads_the_three_line_header(text):
    assert train._header_meta(text) == {"title": "Some Episode", "show": "The Daily",
                                        "date": "2026-09-04"}


def test_header_meta_without_a_header_is_empty():
    assert train._header_meta(NO_HEADER) == {"title": "", "show": "", "date": ""}
    assert train._header_meta("") == {"title": "", "show": "", "date": ""}


def test_header_meta_two_lines_without_show_date_keeps_title_only():
    assert train._header_meta("Title\nnot a show/date line\n") == {"title": "Title", "show": "",
                                                                  "date": ""}


# ---- fixtures ----------------------------------------------------------------

@pytest.fixture
def transcript(tmp_path) -> Path:
    p = tmp_path / "2026-09-04 - Some Episode.txt"
    p.write_text(HEADER_EMDASH, encoding="utf-8")
    return p


@pytest.fixture
def stub_generate(monkeypatch):
    """Replace the paid call with a stub; returns the dict of what it saw."""
    seen: dict = {}

    def fake(text, meta, api_key, model=tr.DEFAULT_MODEL):
        seen.update(text=text, meta=dict(meta), key=api_key, model=model)
        return tr.TrainingResult(outline={"title": meta["title"], "slides": [{"kind": "callout"}]},
                                 study_guide_md="# guide\n")

    monkeypatch.setattr(tr, "generate_training", fake)
    return seen


@pytest.fixture
def stub_render(monkeypatch):
    """Replace the pptx renderer with one that writes a marker file."""
    calls: list[tuple[str, Path]] = []

    def fake(outline, theme, out_path):
        calls.append((theme, Path(out_path)))
        Path(out_path).write_bytes(b"PK-fake")
        return Path(out_path)

    monkeypatch.setattr(deck_render, "render_pptx", fake)
    return calls


def _last4(key) -> str:
    return (key or "")[-4:]


@pytest.fixture
def env_key(monkeypatch) -> str:
    """A made-up key in the environment, the way a shell or CI would pass it."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-2222")
    return "2222"


# ---- key lookup order ----------------------------------------------------------

def test_key_is_never_taken_from_argv(sori_home, transcript, stub_generate, stub_render, capsys):
    # Same policy as settings.py: no --api-key flag, no positional key. Exit 2,
    # the paid call is never reached, and the pasted key is not echoed back
    # (argparse's stock usage error would have printed it).
    for argv in ([str(transcript), "--api-key", "sk-flag-1111"],
                 [str(transcript), "sk-flag-1111"]):
        assert train.main(argv) == 2
        out, err = capsys.readouterr()
        assert out == "" and err.startswith("!! unrecognized arguments")
        assert "1111" not in err and "ANTHROPIC_API_KEY" in err
    assert "key" not in stub_generate
    assert stub_render == []


def test_env_beats_saved(sori_home, monkeypatch, transcript, stub_generate, stub_render):
    (sori_home / "credentials.json").write_text(json.dumps({"anthropic_api_key": "sk-saved-3333"}),
                                                encoding="utf-8")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-2222")
    assert train.main([str(transcript)]) == 0
    assert _last4(stub_generate["key"]) == "2222"


def test_saved_key_in_sori_home_is_the_fallback(sori_home, transcript, stub_generate, stub_render):
    (sori_home / "credentials.json").write_text(json.dumps({"anthropic_api_key": "sk-saved-3333"}),
                                                encoding="utf-8")
    assert train.main([str(transcript)]) == 0
    assert _last4(stub_generate["key"]) == "3333"


def test_saved_key_is_read_from_sori_home_not_the_user_profile(sori_home, transcript, stub_generate,
                                                                 stub_render, monkeypatch):
    # An empty SORI_HOME means "no saved key" even if the real profile had one.
    assert train._sori_key() is None
    assert train.main([str(transcript)]) == 2


# ---- exit codes ------------------------------------------------------------------

def test_exit_2_when_transcript_is_missing(sori_home, tmp_path, capsys):
    assert train.main([str(tmp_path / "nope.txt")]) == 2
    assert "transcript not found" in capsys.readouterr().err


def test_exit_2_when_no_key_anywhere(sori_home, transcript, stub_generate, capsys):
    assert train.main([str(transcript)]) == 2
    err = capsys.readouterr().err
    assert "no Claude API key" in err
    assert "key" not in stub_generate, "the paid call must not be reached without a key"


def test_exit_1_on_training_generation_error(sori_home, transcript, monkeypatch, env_key, stub_render,
                                             capsys):
    def boom(*a, **k):
        raise tr.TrainingGenerationError("That Claude API key was rejected")

    monkeypatch.setattr(tr, "generate_training", boom)
    assert train.main([str(transcript)]) == 1
    assert "!! That Claude API key was rejected" in capsys.readouterr().err
    assert stub_render == [], "nothing rendered after a failed call"


def test_exit_0_writes_pptx_and_md(sori_home, transcript, tmp_path, env_key, stub_generate, stub_render,
                                   capsys):
    out = tmp_path / "out"
    # deck_render.DEFAULT_THEME, not a branded name: a public clone has no
    # engine/ and so no "dark", and this test is not about theming.
    rc = train.main([str(transcript), "--out", str(out),
                     "--theme", deck_render.DEFAULT_THEME])
    assert rc == 0
    pptx = out / "2026-09-04 - Some Episode.pptx"
    md = out / "2026-09-04 - Some Episode.md"
    assert pptx.is_file() and md.is_file()
    assert md.read_text(encoding="utf-8") == "# guide\n"
    assert stub_render == [(deck_render.DEFAULT_THEME, pptx)]
    assert stub_generate["meta"] == {"title": "Some Episode", "show": "The Daily", "date": "2026-09-04"}
    printed = capsys.readouterr().out
    assert "deck :" in printed and "guide:" in printed
    assert env_key not in printed, "the key is never printed"


def test_overrides_beat_the_header(sori_home, transcript, tmp_path, env_key, stub_generate, stub_render):
    rc = train.main([str(transcript), "--out", str(tmp_path / "o"),
                     "--title", "Ep. 12", "--show", "My Show", "--date", "2026-09-05"])
    assert rc == 0
    assert stub_generate["meta"] == {"title": "Ep. 12", "show": "My Show", "date": "2026-09-05"}
    # A dotted title keeps its full name (regression: with_suffix() once cut it to "Ep").
    assert stub_render[0][1].name == "2026-09-05 - Ep. 12.pptx"
    assert (tmp_path / "o" / "2026-09-05 - Ep. 12.md").is_file()


# ---- spend guard -----------------------------------------------------------------

def test_spend_guard_a_live_call_is_refused_by_the_fake_client(sori_home, monkeypatch, transcript,
                                                                 stub_render):
    """With a key present and generate_training NOT stubbed, the only thing
    between train.py and a bill is conftest's fake anthropic module. Prove it
    fires before any request is built."""
    from conftest import SpendGuard

    fake = sys.modules["anthropic"]
    assert getattr(fake, "__sori_fake__", False), "the real anthropic package leaked into the tests"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-2222")

    with pytest.raises(SpendGuard):
        train.main([str(transcript)])
    assert stub_render == [], "nothing rendered when the client refused to build"


# ---- the key-free outline route (Claude-native door) -------------------------

OUTLINE = {"deck_title": "T",
           "slides": [{"kind": "content", "heading": f"s{i}"} for i in range(6)],
           "study_guide_markdown": "# g\n"}


def test_brief_prints_rules_and_schema(capsys):
    assert train.main(["--brief"]) == 0
    out = capsys.readouterr().out
    assert "Every claim, quote, and number must come from the transcript" in out
    assert '"study_guide_markdown"' in out and '"slides"' in out


def test_outline_renders_without_any_key(transcript, tmp_path, stub_render, monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # generate_training is left live on purpose: this route must never reach it.
    outline = tmp_path / "outline.json"
    outline.write_text(json.dumps(OUTLINE), encoding="utf-8")
    code = train.main([str(transcript), "--outline", str(outline), "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert code == 0 and "no API call" in out
    assert stub_render and stub_render[0][1].name == "2026-09-04 - Some Episode.pptx"
    assert (tmp_path / "out" / "2026-09-04 - Some Episode.md").read_text(encoding="utf-8") == "# g"


def test_outline_rejects_bad_shapes(transcript, tmp_path, stub_render, capsys):
    for bad in ({"deck_title": "T", "slides": [], "study_guide_markdown": "g"},
                {**OUTLINE, "slides": OUTLINE["slides"][:3]},
                {**OUTLINE, "slides": [{"kind": "hero"}] * 6},
                {**OUTLINE, "slides": [{"kind": "quote"}] * 6},
                {**OUTLINE, "study_guide_markdown": ""}):
        outline = tmp_path / "o.json"
        outline.write_text(json.dumps(bad), encoding="utf-8")
        assert train.main([str(transcript), "--outline", str(outline)]) == 1
        assert capsys.readouterr().err.startswith("!! ")
    assert stub_render == []


def test_outline_unreadable_is_usage_error(transcript, tmp_path, capsys):
    assert train.main([str(transcript), "--outline", str(tmp_path / "missing.json")]) == 2
    assert "couldn't read outline" in capsys.readouterr().err


# ---- visual kinds: full_bleed / data / scorecard / chart --------------------
#
# These four were admitted to SLIDE_KINDS on the condition that the sourcing
# guard survives as per-kind structure rather than a blanket ban (see the
# SLIDE_KINDS comment in training.py). What follows pins that structure: the
# shapes that make a fabricated figure easy must still be refused.

def _outline_with(slide: dict) -> dict:
    """A minimal valid outline whose first slide is the one under test."""
    filler = [{"kind": "content", "heading": f"s{i}"} for i in range(5)]
    return {"deck_title": "T", "slides": [slide] + filler,
            "study_guide_markdown": "# g\n"}


def _run_outline(tmp_path, transcript, outline: dict) -> int:
    path = tmp_path / "o.json"
    path.write_text(json.dumps(outline), encoding="utf-8")
    return train.main([str(transcript), "--outline", str(path), "--out", str(tmp_path / "out")])


GOOD_DATA = {"kind": "data", "eyebrow": "E", "rail_label": "OUTAGE",
             "hero_stat": {"num": "90", "label": "minutes"},
             "stats": [{"num": "3", "label": "down"}]}
GOOD_CHART = {"kind": "chart", "heading": "H", "unit": "%",
              "data": [{"label": "a", "value": 100}, {"label": "b", "value": 98.6},
                       {"label": "c", "value": 5}]}
GOOD_SCORECARD = {"kind": "scorecard", "heading": "H",
                  "rows": [{"label": "r1", "level": 0, "note": "n"}]}
GOOD_FULL_BLEED = {"kind": "full_bleed", "heading": "Part two", "lede": "l"}


@pytest.mark.parametrize("slide", [GOOD_DATA, GOOD_CHART, GOOD_SCORECARD, GOOD_FULL_BLEED],
                         ids=["data", "chart", "scorecard", "full_bleed"])
def test_visual_kinds_are_accepted(transcript, tmp_path, stub_render, slide):
    assert _run_outline(tmp_path, transcript, _outline_with(slide)) == 0
    assert stub_render, "the render was never reached"


@pytest.mark.parametrize("slide, ids", [
    # a stat slide with no stat is the fabrication shape we care about
    ({"kind": "data", "hero_stat": {}}, "data-without-hero"),
    ({"kind": "data", "hero_stat": {"num": "90"},
      "stats": [{"label": "no number"}]}, "data-satellite-without-num"),
    # two points is not a comparison, it is a pair of numbers in a bar costume
    ({"kind": "chart", "data": [{"label": "a", "value": 1},
                                {"label": "b", "value": 2}]}, "chart-under-three"),
    ({"kind": "chart", "data": [{"label": "a", "value": "lots"},
                                {"label": "b", "value": 2},
                                {"label": "c", "value": 3}]}, "chart-non-numeric"),
    ({"kind": "scorecard", "rows": []}, "scorecard-without-rows"),
    ({"kind": "scorecard", "rows": [{"label": "r", "level": 9}]}, "scorecard-level-out-of-range"),
])
def test_visual_kinds_reject_fabrication_shapes(transcript, tmp_path, stub_render, capsys, slide, ids):
    assert _run_outline(tmp_path, transcript, _outline_with(slide)) == 1
    assert capsys.readouterr().err.startswith("!! ")
    assert stub_render == []


def test_only_one_full_bleed_per_deck(transcript, tmp_path, stub_render, capsys):
    """deckgen budgets 3 polychrome moments and cover/closing already spend two."""
    outline = _outline_with(GOOD_FULL_BLEED)
    outline["slides"][1] = dict(GOOD_FULL_BLEED)
    assert _run_outline(tmp_path, transcript, outline) == 1
    assert "full_bleed" in capsys.readouterr().err
    assert stub_render == []


def test_full_bleed_flips_to_the_contrasting_mode():
    """In baek the colour field is a pale tint on a white ground -- invisible.
    The section break renders dark so it actually reads as a break."""
    spec = deck_render._slide_spec(GOOD_FULL_BLEED, "light")
    assert spec["mode"] == "dark"
    # every other kind stays in the deck's own mode
    assert deck_render._slide_spec(GOOD_DATA, "light")["mode"] == "light"


def test_bridge_coerces_visual_payloads():
    """The bridge drops members deckgen would render as blanks or crash on."""
    spec = deck_render._slide_spec(
        {**GOOD_DATA, "stats": [{"num": "3", "label": "ok"}, {"label": "no num"},
                                {"num": "4"}, {"num": "5"}]}, "light")
    assert [s["num"] for s in spec["stats"]] == ["3", "4"]      # dropped + capped at 2

    spec = deck_render._slide_spec(
        {**GOOD_CHART, "data": [*GOOD_CHART["data"], {"label": "bad", "value": None}]}, "light")
    assert len(spec["data"]) == 3 and all(isinstance(d["value"], float) for d in spec["data"])

    spec = deck_render._slide_spec({**GOOD_SCORECARD, "rows": [{"label": "r", "level": 99}]}, "light")
    assert spec["rows"][0]["level"] == 3                         # clamped into the trigram range
