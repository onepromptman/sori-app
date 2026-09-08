"""app.training_paths_for: the deck and study-guide names for one episode.

Regression for the auto-train chain (window worker and ``--sweep`` alike):
the paths used to be built with ``Path.with_suffix()``, which treats the text
after the LAST dot of a title as the suffix. "Ep. 12" and "Ep. 1" on the same
day both collapsed to ``<date> - Ep.pptx``, and ``run_training`` then returned
the first episode's deck for the second one without a call. No network, no
spend: only the path function runs.
"""
from __future__ import annotations

import pytest

DOTTED = [
    ("Ep. 12", "2026-09-05 - Ep. 12"),
    ("Vol. 3, Pt. 2", "2026-09-05 - Vol. 3, Pt. 2"),
    ("U.S. policy in 2026", "2026-09-05 - U.S. policy in 2026"),
    ("Trailing dots...", "2026-09-05 - Trailing dots"),  # _safe_name strips trailing dots
]


@pytest.mark.parametrize("title,stem", DOTTED, ids=[t for t, _ in DOTTED])
def test_dotted_titles_keep_their_full_name(app_mod, title, stem):
    pptx, md = app_mod.training_paths_for("Show", {"date": "2026-09-05", "title": title})
    assert pptx.name == f"{stem}.pptx"
    assert md.name == f"{stem}.md"
    assert pptx.parent == md.parent == app_mod.trainings_dir() / "Show"


def test_two_dotted_episodes_on_one_day_do_not_collide(app_mod):
    a = app_mod.training_paths_for("Show", {"date": "2026-09-05", "title": "Ep. 1"})
    b = app_mod.training_paths_for("Show", {"date": "2026-09-05", "title": "Ep. 2"})
    assert a[0] != b[0] and a[1] != b[1]
    assert {a[0].name, b[0].name} == {"2026-09-05 - Ep. 1.pptx", "2026-09-05 - Ep. 2.pptx"}


def test_paths_match_the_transcript_naming(app_mod):
    ep = {"date": "2026-09-05", "title": "Ep. 12"}
    txt = app_mod.transcript_path_for("Show", ep)
    pptx, _ = app_mod.training_paths_for("Show", ep)
    assert txt.stem == pptx.stem == "2026-09-05 - Ep. 12"


def test_missing_title_and_date_fall_back(app_mod):
    pptx, md = app_mod.training_paths_for("Show", {})
    assert pptx.name == "undated - untitled.pptx" and md.name == "undated - untitled.md"
