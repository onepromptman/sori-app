"""Package Sori for a static host and a local desktop assistant."""

import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
APP_FILES = (
    "index.html",
    "sori.css",
    "app.js",
    "storage.js",
    "sources/index.js",
    "slides/index.js",
    "transcription/index.js",
    "transcription/tab-audio.js",
    "transcription/worker.js",
)
SHARED_ASSETS = (
    "assets/rosette-baek.png",
    "assets/keyfret-cobalt.png",
    "fonts/gowun-batang.woff2",
    "fonts/ibm-plex-mono.woff2",
    "fonts/ibm-plex-sans.woff2",
    "fonts/ibm-plex-sans-semibold.woff2",
    "fonts/OFL.txt",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output", type=Path, help="New directory for the static site and ZIPs"
    )
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True)
    files = {name: ROOT / "browser" / name for name in APP_FILES}
    files.update(
        {f"design/{Path(name).name}": ROOT / "ui" / name for name in SHARED_ASSETS}
    )
    files["LICENSE.txt"] = ROOT / "LICENSE"
    web_zip = output / "Sori-web.zip"
    setup_zip = output / "Sori-setup.zip"
    with (
        ZipFile(web_zip, "x", compression=ZIP_DEFLATED) as web,
        ZipFile(setup_zip, "x", compression=ZIP_DEFLATED) as setup,
    ):
        for name in ("SETUP.txt", "serve.cjs"):
            setup.write(ROOT / "browser" / name, name)
        for name, source in files.items():
            data = source.read_bytes()
            target = output / "site" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            web.writestr(name, data)
            setup.writestr(f"site/{name}", data)
    checksums = "".join(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n"
        for archive in (web_zip, setup_zip)
    )
    (output / "SHA256SUMS.txt").write_text(checksums, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
