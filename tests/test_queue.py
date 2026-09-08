"""Behavioural tests of the transcription queue.

Nine groups, one test function each (T1..T9): priority order, dismiss for a
never-queued / queued / mid-run episode, no ``cancelled`` snapshot leak,
re-submit after dismiss, bulk dismiss, the twin-name heuristic, the
``add_show`` warning, and ``sweep()``. Every test builds its own ``Api`` over
a fresh ``SORI_HOME`` (see ``conftest.py``), with a fake, cancellable
transcriber and a fake feed parser: no network, no Whisper, no API spend,
and each group passes on its own (``-k T3``).

    py -m pytest tests/test_queue.py -q
    py tests/test_queue.py                (same thing, direct)
"""
from __future__ import annotations

import time

import pytest

SHOW_ID = "s1"


class Harness:
    """One Api + its worker, with the event stream captured instead of pushed
    to a window, and the helpers the scenarios keep reaching for."""

    def __init__(self, app_mod, fake_transcriber, seeded_show):
        self.app = app_mod
        self.show = seeded_show
        self.settings = app_mod.load_store()["settings"]
        self.made = fake_transcriber.made
        self.transcriber = fake_transcriber
        self.events: list[tuple[str, dict]] = []
        self.api = app_mod.Api()
        self.api._emit = lambda name, payload: self.events.append((name, dict(payload)))
        self.api._worker._emit = self.api._emit
        self.worker = self.api._worker

    # -- fakes' knobs --------------------------------------------------------
    def ep(self, i: int) -> dict:
        from conftest import EPISODES
        return {**EPISODES[i - 1], "show_id": SHOW_ID, "show_name": self.show["name"]}

    def submit_auto(self, i: int) -> str:
        return self.worker.submit(self.show, self.ep(i), self.settings)

    # -- observations --------------------------------------------------------
    def status_of(self, eid: str):
        return self.worker.states().get(eid, {}).get("status")

    def done_order(self) -> list[str]:
        return [p["id"] for n, p in self.events if n == "job" and p.get("status") == "done"]

    def seen(self) -> set[str]:
        return set(self.app._find_show(self.app.load_store(), SHOW_ID).get("seen", []))

    def emitted(self, eid: str, status: str) -> bool:
        return any(p.get("id") == eid and p.get("status") == status for _, p in self.events)

    @staticmethod
    def wait_until(pred, timeout: float = 15.0) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if pred():
                return True
            time.sleep(0.05)
        return False

    def wait_done(self, eid: str, timeout: float = 20.0) -> bool:
        return self.wait_until(lambda: self.status_of(eid) == "done", timeout)


@pytest.fixture
def h(app_mod, fake_feed, fake_transcriber, seeded_show) -> Harness:
    fake_transcriber.seconds = 0.6  # long enough to queue behind, short enough to run often
    return Harness(app_mod, fake_transcriber, seeded_show)


def test_T1_priority_manual_pick_runs_before_earlier_auto_pushes(h: Harness):
    h.submit_auto(1)                                   # auto, starts now
    assert h.wait_until(lambda: h.worker._running == "e1", 5)
    h.submit_auto(2)                                   # auto, queued
    r = h.api.transcribe_episode(SHOW_ID, h.ep(3))     # manual, queued later
    assert r["ok"], r
    assert h.status_of("e2") == "queued" and h.status_of("e3") == "queued"
    assert h.wait_until(lambda: len(h.done_order()) >= 3, 20)
    assert h.done_order() == ["e1", "e3", "e2"]


def test_T2_dismiss_an_episode_that_was_never_queued(h: Harness):
    h.transcriber.seconds = 0.1
    h.submit_auto(1)                                   # a transcribed episode is seen too
    assert h.wait_done("e1")

    r = h.api.dismiss_episode(SHOW_ID, "e4")
    assert r["ok"] and r["data"]["status"] == "dismissed", r
    assert "e4" in h.seen()
    offered = {e["id"] for e in h.app.check_all()["episodes"]}
    assert "e4" not in offered
    assert "e1" not in offered, "transcribed => seen"
    assert {"e2", "e3", "e5"} <= offered


def test_T3_dismiss_a_queued_not_yet_running_episode(h: Harness):
    h.submit_auto(5)                                   # starts now
    assert h.wait_until(lambda: h.worker._running == "e5", 5)
    h.submit_auto(6)                                   # queued
    assert h.status_of("e6") == "queued"

    r = h.api.dismiss_episode(SHOW_ID, "e6")
    assert r["data"]["status"] == "dismissed", r
    assert "e6" not in h.worker.states(), "row gone from the job table now"

    assert h.wait_done("e5")
    time.sleep(0.3)                                    # let the loop drain past e6
    assert "e6" not in h.worker.states(), "still gone after the loop drained it"
    assert not h.emitted("e6", "cancelled"), "never got a 'cancelled' snapshot"
    assert "e6" not in h.made, "never transcribed"
    assert "e6" in h.seen()


def _dismiss_running(h: Harness, eid: str = "e7") -> dict:
    h.submit_auto(int(eid[1:]))
    assert h.wait_until(lambda: h.worker._running == eid, 5), f"{eid} should be running"
    return h.api.dismiss_episode(SHOW_ID, eid)


def test_T4_dismiss_the_episode_that_is_running_right_now(h: Harness):
    r = _dismiss_running(h, "e7")
    assert r["data"]["status"] == "stopping", r
    assert h.wait_until(lambda: "e7" not in h.worker.states() and h.worker._running is None, 10), \
        "row dropped once cancel landed"
    assert h.emitted("e7", "dismissed")
    assert "e7" not in h.made, "no transcript written"
    assert "e7" in h.seen()


def test_T5_a_deliberate_resubmit_after_dismiss_still_works(h: Harness):
    _dismiss_running(h, "e7")
    assert h.wait_until(lambda: h.worker._running is None and "e7" not in h.worker.states(), 10)
    h.events.clear()

    r = h.api.transcribe_episode(SHOW_ID, h.ep(7))
    assert r["ok"] and r["data"]["status"] == "queued", r
    assert h.wait_done("e7")
    assert "e7" in h.made


def test_T6_bulk_dismiss(h: Harness):
    r = h.api.dismiss_episodes([{"show_id": SHOW_ID, "id": "zz1"},
                                {"show_id": SHOW_ID, "id": "zz2"},
                                {"bad": 1}])
    assert r["ok"], r
    assert r["data"]["dismissed"] == 2, "counts valid items only"
    assert {"zz1", "zz2"} <= h.seen()


def test_T7_same_show_name_heuristic(app_mod):
    f = app_mod._same_show_name
    assert f("The AI Daily Brief: Artificial Intelligence News and Analysis",
             "The AI Daily Brief: Artificial Intelligence News"), "the two AI Daily Brief entries match"
    assert not f("The Daily", "The Daily Show")
    assert not f("AI", "AI Daily"), "short names need an exact match"
    assert f("Lex", "Lex")


def test_T8_add_show_warns_but_does_not_block_on_a_twin(h: Harness, fake_feed):
    fake_feed("Fake Show: Extra Words")
    r = h.api.add_show("https://y/feed")
    assert r["ok"] and r["data"]["name"] == "Fake Show: Extra Words", str(r)[:200]
    assert "Fake Show" in (r["data"].get("warning") or ""), "carries a warning naming the twin"

    fake_feed("Totally Different")
    r = h.api.add_show("https://z/feed")
    assert r["ok"] and "warning" not in r["data"], "unrelated show has no warning"


def test_T9_sweep_still_runs_with_the_worker_in_place(h: Harness):
    h.transcriber.seconds = 0.05
    assert h.app.sweep() == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
