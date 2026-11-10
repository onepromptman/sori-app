"""Mistaken command-line keys are refused without appearing in diagnostics."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("args", [["set", "{marker}"], ["{marker}"], ["set", "--key", "{marker}"]])
def test_api_key_usage_does_not_echo_value(tmp_path, monkeypatch, args):
    marker = "fictional-key-redaction-canary"
    monkeypatch.setenv("SORI_HOME", str(tmp_path))
    script = Path(__file__).resolve().parents[1] / "settings.py"
    result = subprocess.run(
        [sys.executable, str(script), "api-key", *(arg.format(marker=marker) for arg in args)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 2
    assert marker not in result.stdout + result.stderr
    assert not (tmp_path / "credentials.json").exists()
