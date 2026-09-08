#!/usr/bin/env python3
"""
Render the Sori UI in a browser with a fake backend, for layout work and
README screenshots. The real app runs inside WebView2, which is awkward to
screenshot (PrintWindow returns stale paint; a background process cannot
bring it to the foreground). This serves a copy of ui/ with stub.js loaded
BEFORE app.js, so app.js's 8-second bridge wait finds window.pywebview.api
immediately and renders the sample queue in stub.js.

    py tools/ui-preview/preview.py              # serve on http://127.0.0.1:8766/preview.html
    py tools/ui-preview/preview.py --shot out.png   # also write a 1400x860 PNG via headless Edge

Open the URL in Chrome (Claude in Chrome works: navigate, javascript_tool,
screenshot). Edit stub.js to stage other row states. Never point this at
real subscriptions; the stub data is what a public screenshot may contain.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UI = ROOT / "ui"
STUB = Path(__file__).with_name("stub.js")
EDGE = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]


def build(dest: Path) -> Path:
    shutil.copytree(UI, dest, dirs_exist_ok=True)
    shutil.copy2(STUB, dest / "stub.js")
    html = (dest / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<script[^>]*src="[^"]*app\.js"', html)
    if not m:
        sys.exit("ui/index.html: app.js script tag not found")
    html = html[: m.start()] + '<script src="stub.js"></script>\n' + html[m.start():]
    out = dest / "preview.html"
    out.write_text(html, encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--shot", help="write a PNG of the preview via headless Edge, then exit")
    ap.add_argument("--size", default="1400,860")
    args = ap.parse_args()

    dest = Path(tempfile.mkdtemp(prefix="sori-preview-"))
    build(dest)
    handler = partial(SimpleHTTPRequestHandler, directory=str(dest))
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    url = f"http://127.0.0.1:{args.port}/preview.html"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print("serving", url)

    if args.shot:
        edge = next((e for e in EDGE if e.exists()), None)
        if not edge:
            sys.exit("Edge not found; open the URL in a browser instead")
        out = Path(args.shot).resolve()
        subprocess.run([str(edge), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        f"--window-size={args.size}", "--virtual-time-budget=6000",
                        f"--screenshot={out}", url], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("wrote", out if out.exists() else "(nothing: Edge failed)")
        srv.shutdown()
        return 0 if out.exists() else 1

    print("Ctrl+C to stop")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        srv.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
