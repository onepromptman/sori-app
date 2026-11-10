"""Public packaging must not ingest untracked user state or private modules."""

import subprocess

import pytest

import public_release


def test_snapshot_excludes_untracked_private_data(tmp_path):
    repo, out = tmp_path / "repo", tmp_path / "out"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "app.py").write_text("pass\n")
    (repo / "credentials.json").write_text("{}")
    (repo / "engine").mkdir()
    (repo / "engine/private.py").write_text("pass\n")
    subprocess.run(["git", "add", "app.py"], cwd=repo, check=True)
    assert public_release.snapshot(repo, out) == ["app.py"]
    assert list(out.iterdir()) == [out / "app.py"]


def test_snapshot_refuses_tracked_state(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "credentials.json").write_text("{}")
    subprocess.run(["git", "add", "credentials.json"], cwd=tmp_path, check=True)
    with pytest.raises(ValueError, match="private"):
        public_release.snapshot(tmp_path, tmp_path / "out")


def test_existing_binary_cannot_be_reused(monkeypatch):
    monkeypatch.setattr("sys.argv", ["package.py", "--no-build"])
    assert public_release.main() == 2
