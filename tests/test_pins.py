"""The requirements*.txt install lists carry the same exact pins as pyproject.toml.

pyproject.toml is the one place pins live; the .txt files exist for the
README's `pip install -r` routes. Without exact pins there, a fresh install
pulled newer yt-dlp and anthropic releases than the ones the app is tested on.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQ_FILES = ("requirements.txt", "requirements-app.txt", "requirements-captions.txt")


def _pyproject_pins() -> dict[str, str]:
    proj = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    reqs = list(proj["dependencies"])
    for group in proj["optional-dependencies"].values():
        reqs += group
    pins: dict[str, str] = {}
    for req in reqs:
        name, version = req.split("==")
        pins[name.strip().lower()] = version.strip()
    return pins


def test_every_requirements_line_matches_a_pyproject_pin():
    pins = _pyproject_pins()
    for fname in REQ_FILES:
        for raw in (ROOT / fname).read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith("-r "):
                continue
            m = re.fullmatch(r"([A-Za-z0-9._-]+)==([^\s;]+)", line)
            assert m, f"{fname}: {line!r} is not an exact pin"
            name, version = m.group(1).lower(), m.group(2)
            assert pins.get(name) == version, (
                f"{fname} pins {name}=={version}, pyproject says {pins.get(name)}"
            )
