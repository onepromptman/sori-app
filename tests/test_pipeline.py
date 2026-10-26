"""The training pipeline after the transcript: ledger, brief gate, design hand-offs, CLI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import sori
from pipeline import brief as briefmod
from pipeline import cli, design, ledger

TRANSCRIPT = (
    "Welcome back.\nShow — 2026-10-01\nhttps://example.com/ep\n\n"
    "Today we talk about agents. The thing people miss is that an agent is a loop, not a prompt. "
    "We saw a forty percent drop in handoff time after the pilot. "
    "Verification is the whole job; if you can't check it, don't ship it. "
    "Start with one boring task and automate only that."
)

GOOD_BRIEF = """# Brief: Agents are loops
show: Show    date: 2026-10-01    source: https://example.com/ep

## Objectives
- After this session a recruiter can explain why an agent is a loop, not a prompt
- After this session a recruiter can pick one boring task to automate first
- After this session a recruiter can name one way to verify an AI's output

## Audience
Recruiters and people-ops, no coding background, 30 minutes.

## DO step
In pairs, write one task you repeat weekly and draft the three checks you would run on an AI
doing it. The artifact they leave with is that one-page check sheet.

## Evidence
- [01:10] "an agent is a loop, not a prompt" — the mental model the whole session rests on
- [03:42] "forty percent drop in handoff time after the pilot" — the one number stated
- [05:05] "if you can't check it, don't ship it" — verification as the job
- [06:30] "Start with one boring task and automate only that." — the DO step's rule

## Leave out
The model-benchmark tangent; the founder story.

## Slide recommendation
1. [cover] Agents are loops
2. [agenda] three ideas, one exercise
3. [content] loop, not prompt
4. [quote] if you can't check it, don't ship it
5. [content_stat] forty percent
6. [exercise] the check sheet
7. [closing] one boring task
"""


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    return tmp_path


# --- ledger -----------------------------------------------------------------

def test_ledger_records_and_tracks_furthest_stage(home):
    ledger.record("Show", "ep1", "discovered", "sweep", title="E1")
    ledger.record("Show", "ep1", "transcribed", "sweep", title="E1", artifact=home / "Transcripts" / "x.txt")
    ledger.record("Show", "ep2", "transcribed", "sweep", title="E2")
    ledger.record("Show", "ep2", "skipped", "curator", note="no DO step")
    cur = ledger.latest()
    assert cur["ep1"]["stage"] == "transcribed"
    assert cur["ep1"]["artifact"] == str(Path("Transcripts") / "x.txt")   # relative to SORI_HOME
    assert cur["ep2"]["stage"] == "skipped"
    assert [r["episode_id"] for r in ledger.awaiting("transcribed", "triaged")] == ["ep1"]
    s = ledger.summary()
    assert s["transcribed"] == 1 and s["skipped"] == 1
    with pytest.raises(ValueError):
        ledger.record("Show", "ep3", "nonsense", "x")


def test_ledger_survives_a_torn_line(home):
    ledger.record("Show", "ep1", "transcribed", "sweep")
    with open(ledger.ledger_path(), "a", encoding="utf-8") as f:
        f.write('{"at": "2026-01-01T00:00:00Z", "epis')
    ledger.record("Show", "ep1", "briefed", "ld-architect")
    assert ledger.latest()["ep1"]["stage"] == "briefed"


def test_episode_dir_is_safe_and_under_trainings(home):
    d = ledger.episode_dir("The Show: Live", {"date": "2026-10-01", "title": 'Ep "1" <a/b>'})
    assert d.is_dir()
    assert d.parent.parent == home / "Trainings"
    assert ":" not in d.name and "/" not in d.name.replace(str(home), "")


# --- brief gate --------------------------------------------------------------

def test_good_brief_passes():
    rep = briefmod.check(GOOD_BRIEF, TRANSCRIPT)
    assert rep.ok, rep.findings
    assert rep.checked_quotes == 4
    b = briefmod.parse(GOOD_BRIEF)
    assert b.title == "Agents are loops"
    assert b.meta["date"] == "2026-10-01"
    assert [s["kind"] for s in b.slides][:2] == ["cover", "agenda"]
    assert b.evidence[1]["stamp"] == "03:42"


def test_paraphrased_quote_fails_the_gate():
    bad = GOOD_BRIEF.replace('"forty percent drop in handoff time after the pilot"',
                             '"a 40% drop in handoff time"')
    rep = briefmod.check(bad, TRANSCRIPT)
    assert not rep.ok
    assert any("not verbatim" in f for f in rep.findings)


def test_curly_quotes_and_whitespace_still_match():
    curly = GOOD_BRIEF.replace('"if you can\'t check it, don\'t ship it"', "“if you  can’t check it,\n  don’t ship it”")
    assert briefmod.check(curly, TRANSCRIPT).ok


def test_structural_findings():
    no_do = GOOD_BRIEF.replace("## DO step\n", "## DO step\nTalk about it.\n## Removed\n").replace(
        "In pairs, write one task", "In pairs, discuss one task").replace("The artifact they leave with", "They talk about")
    rep = briefmod.check(no_do, TRANSCRIPT)
    assert any("artifact" in f for f in rep.findings)
    short = GOOD_BRIEF.split("## Slide recommendation")[0] + "## Slide recommendation\n1. [cover] x\n"
    rep = briefmod.check(short, TRANSCRIPT)
    assert any("slide lines" in f for f in rep.findings)
    missing = GOOD_BRIEF.replace("## Leave out", "## Something else")
    rep = briefmod.check(missing, TRANSCRIPT)
    assert any("Leave out" in f for f in rep.findings)
    badkind = GOOD_BRIEF.replace("[agenda]", "[hologram]")
    assert any("hologram" in f for f in briefmod.check(badkind, TRANSCRIPT).findings)


def test_template_parses_as_a_brief_skeleton():
    t = briefmod.TEMPLATE.format(title="T", show="S", date="2026-01-01", source="u")
    b = briefmod.parse(t)
    assert set(briefmod.REQUIRED) <= set(b.sections)


# --- design hand-offs -----------------------------------------------------

def _episode(home) -> Path:
    ep = ledger.episode_dir("Show", {"date": "2026-10-01", "title": "Agents are loops"})
    (ep / "brief.md").write_text(GOOD_BRIEF, encoding="utf-8")
    tdir = home / "Transcripts" / "Show"
    tdir.mkdir(parents=True)
    (tdir / (ep.name + ".txt")).write_text(TRANSCRIPT, encoding="utf-8")
    return ep


@pytest.mark.parametrize("backend", design.BACKENDS)
def test_every_backend_writes_a_handoff(home, backend):
    ep = _episode(home)
    design.save_config({"design_system_url": "https://claude.ai/artifact/x", "dsign_root": "/r", "dsign_theme": "baek"})
    out = design.handoff(ep, backend)
    assert out == ep / "handoff" / backend
    assert (out / "brief.md").exists() and (out / "evidence.md").exists() and (out / "README.md").exists()
    readme = (out / "README.md").read_text()
    assert "if you can't check it, don't ship it" in (out / "evidence.md").read_text()
    if backend == "chatslide":
        doc = (out / "source-document.md").read_text()
        assert "### Slide 6: the check sheet" in doc and "forty percent" in doc
    if backend == "dsign-html":
        m = json.loads((out / "slide-map.json").read_text())
        assert m["theme"] == "baek"
        assert m["slides"][0]["master"] == "themes/baek/title.html"
        assert m["slides"][5]["master"] == "themes/baek/steps.html"
    if backend == "claude-design":
        assert "https://claude.ai/artifact/x" in readme


def test_handoff_refuses_a_failing_brief(home):
    ep = _episode(home)
    (ep / "brief.md").write_text(GOOD_BRIEF.replace("forty percent drop", "40% drop"), encoding="utf-8")
    with pytest.raises(design.HandoffError, match="sourcing gate"):
        design.handoff(ep, "offline")
    with pytest.raises(design.HandoffError, match="unknown backend"):
        design.handoff(ep, "powerpoint-2003")


def test_config_roundtrip_and_validation(home):
    assert design.load_config()["design_backend"] == "offline"
    design.save_config({"design_backend": "claude-design"})
    assert design.load_config()["design_backend"] == "claude-design"
    with pytest.raises(ValueError):
        design.save_config({"design_backend": "canva"})
    with pytest.raises(ValueError):
        design.save_config({"colour": "red"})


# --- CLI ----------------------------------------------------------------------

def test_cli_curate_list_and_ledger_table(home, capsys):
    ledger.record("Show", "ep1", "transcribed", "sweep", title="E1")
    assert cli.main(["curate", "--list"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["curriculum"] is None
    assert [r["episode_id"] for r in data["awaiting_triage"]] == ["ep1"]
    assert cli.main(["curate", "--init"]) == 0
    capsys.readouterr()
    assert (home / "curriculum.md").exists()
    assert cli.main(["curate", "--init"]) == 1          # refuses to overwrite
    capsys.readouterr()
    assert cli.main(["ledger", "add", "ep1", "briefed", "ld-architect", "--show", "Show"]) == 0
    capsys.readouterr()
    assert cli.main(["ledger"]) == 0
    out = capsys.readouterr().out
    assert "briefed" in out and "ep1" not in out.split("\n")[0]


def test_cli_brief_check_and_design(home, capsys):
    ep = _episode(home)
    t = design.find_transcript(ep)
    assert cli.main(["brief-check", str(ep / "brief.md"), str(t)]) == 0
    assert "PASS" in capsys.readouterr().out
    assert cli.main(["design", str(ep), "--backend", "chatslide"]) == 0
    assert "handoff" in capsys.readouterr().out
    assert cli.main(["design", str(ep)]) == 0            # offline, no outline yet -> instructions
    assert "no outline.json yet" in capsys.readouterr().out
    assert cli.main(["design-config", "design_backend", "figma"]) == 0
    assert json.loads(capsys.readouterr().out)["design_backend"] == "figma"


def test_launcher_routes_pipeline_verbs():
    for verb in ("ledger", "curate", "brief-check", "brief-template", "design", "design-config"):
        assert sori.VERBS[verb][0] == "pipeline/cli.py"
        assert sori.VERBS[verb][1] == verb
        assert (sori.ROOT / sori.VERBS[verb][0]).is_file()


def test_folder_names_cannot_smuggle_shell_syntax(home):
    d = ledger.episode_dir("Show", {"date": "2026-10-01", "title": "Ep $(rm -rf ~) `id` x"})
    assert "$" not in d.name and "`" not in d.name


def test_offline_readme_quotes_the_path(home):
    ep = ledger.episode_dir("Show", {"date": "2026-10-01", "title": "it's a 'quoted' title"})
    (ep / "brief.md").write_text(GOOD_BRIEF, encoding="utf-8")
    tdir = home / "Transcripts" / "Show"
    tdir.mkdir(parents=True)
    (tdir / (ep.name + ".txt")).write_text(TRANSCRIPT, encoding="utf-8")
    readme = (design.handoff(ep, "offline") / "README.md").read_text()
    import shlex
    assert shlex.quote(str(ep)) in readme
