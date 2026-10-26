"""app.py --selftest under the launcher's dependency profiles."""
from __future__ import annotations

import app


def _run(monkeypatch, capsys, profile):
    if profile is None:
        monkeypatch.delenv("SORI_PROFILE", raising=False)
    else:
        monkeypatch.setenv("SORI_PROFILE", profile)
    code = app.selftest()
    return code, capsys.readouterr().out


def test_claude_profile_skips_window_and_api_client(monkeypatch, capsys):
    """conftest installs a fake anthropic, so hide it to model the claude profile."""
    import sys
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.setitem(sys.modules, "webview", None)
    code, out = _run(monkeypatch, capsys, "claude")
    assert "profile: claude" in out
    assert "skip  webview" in out and "skip  anthropic" in out
    assert "FAIL  webview" not in out and "FAIL  anthropic" not in out
    # whether it passes overall depends on whisper being installed on this CI
    # box; what matters here is that the two optional ones never fail it.
    assert code in (0, 1)


def test_app_profile_still_requires_everything(monkeypatch, capsys):
    import sys
    monkeypatch.setitem(sys.modules, "webview", None)
    code, out = _run(monkeypatch, capsys, None)
    assert "profile: app" in out
    assert "FAIL  webview" in out
    assert code == 1
