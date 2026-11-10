#!/usr/bin/env python3
"""
webserver.py: serves Sori's UI to a normal browser on this PC.

The UI talks to the same Api class the desktop window uses. This module swaps
the transport: POST /api/<method> instead of the pywebview bridge, and a
server-sent event stream instead of evaluate_js.

Standard library only, so it adds nothing to the install or the exe.

The server can reach the user's API key and files, and any website open in the
browser can send requests to 127.0.0.1, so three checks stand in front of it:

* It binds 127.0.0.1 only, so nothing else on the network can connect.
* The Host header must name this server. That stops a site that points its own
  domain at 127.0.0.1 (DNS rebinding).
* Every API call needs a token that is generated at launch and only written
  into the page this server serves. Other sites cannot read that page, because
  no response here carries CORS headers.

Only one engine may run on a state folder (engine_lock.py). The port is not
that guard: it is how a second launch finds the copy that is already running,
so it can open it in the browser instead of starting again.
"""

from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import logging
import os
import queue
import secrets
import socket
import socketserver
import subprocess
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit

from engine_lock import EngineLock

log = logging.getLogger(__name__)

APP_NAME = "Sori"
HOST = "127.0.0.1"
DEFAULT_PORT = 17654
MAX_BODY_BYTES = 8 * 1024 * 1024
EVENT_BACKLOG = 512
KEEPALIVE_SECONDS = 15

# Spelled out because mimetypes reads the Windows registry, which can map .js
# to text/plain, and browsers refuse that script under nosniff.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".ttf": "font/ttf",
    ".otf": "font/otf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
}


def configured_port() -> int:
    raw = os.environ.get("SORI_PORT", "")
    return int(raw) if raw.isdigit() else DEFAULT_PORT


def home_id(home: Path) -> str:
    """Names a state folder without putting its path in an unauthenticated reply."""
    return hashlib.sha256(str(home).encode("utf-8")).hexdigest()[:16]


def is_running(port: int, home: Path) -> bool:
    """True if a Sori server for this state folder already answers on `port`."""
    conn = http.client.HTTPConnection(HOST, port, timeout=1.5)
    try:
        conn.request("GET", "/health")
        reply = conn.getresponse()
        info = json.loads(reply.read().decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        conn.close()
    return info.get("app") == APP_NAME and info.get("home") == home_id(home)


class EventHub:
    """Fans engine events out to every open tab."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: set[queue.Queue] = set()

    def subscribe(self) -> queue.Queue:
        client: queue.Queue = queue.Queue(EVENT_BACKLOG)
        with self._lock:
            self._clients.add(client)
        return client

    def unsubscribe(self, client: queue.Queue) -> None:
        with self._lock:
            self._clients.discard(client)

    def publish(self, name: str, payload: Any) -> None:
        message = json.dumps({"name": name, "payload": payload}, default=str)
        self._offer(message)

    def close(self) -> None:
        self._offer(None)

    def _offer(self, message: str | None) -> None:
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            try:
                client.put_nowait(message)
            except queue.Full:
                # A stalled tab loses live updates only: the UI also polls
                # job_states while anything is running.
                log.debug("event dropped for a stalled tab")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = APP_NAME
    sys_version = ""
    server: SoriServer

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # The default writes to sys.stderr, which is None in the windowed exe,
        # and the request line would put the event token in a log.
        pass

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            self._json(403, {"ok": False, "error": "Wrong host."})
            return
        parts = urlsplit(self.path)
        path = unquote(parts.path)
        if path == "/health":
            self._json(200, {"app": APP_NAME, "home": self.server.home_id})
        elif path == "/events":
            self._events(parts.query)
        elif path in ("/", "/index.html"):
            self._index()
        else:
            self._static(path)

    def do_POST(self) -> None:  # noqa: N802
        if (
            not self._host_ok()
            or not self._origin_ok()
            or not self._token_ok(self.headers.get("X-Sori-Token", ""))
        ):
            self._refuse(403, "Not allowed.")
            return
        path = urlsplit(self.path).path
        if path == "/quit":
            self._discard_body()
            self._json(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, name="quit", daemon=True).start()
        elif path.startswith("/api/"):
            self._api(path[len("/api/") :])
        else:
            self._refuse(404, "Not found.")

    # -- checks -------------------------------------------------------------

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "").lower() in self.server.allowed_hosts

    def _token_ok(self, candidate: str) -> bool:
        return hmac.compare_digest(candidate.encode("utf-8"), self.server.token.encode("utf-8"))

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in {f"http://{host}" for host in self.server.allowed_hosts}

    # -- routes -------------------------------------------------------------

    def _api(self, method: str) -> None:
        func = self.server.methods.get(method)
        if func is None:
            self._refuse(404, f"No such action: {method}")
            return
        args = self._json_args()
        if args is None:
            return
        self._json(200, func(*args))

    def _json_args(self) -> list | None:
        """Read the request body as a JSON array, or reply with an error and return None."""
        length = self._content_length()
        if length < 0:
            self._refuse(400, "Bad request.")
            return None
        if length > MAX_BODY_BYTES:
            self._refuse(413, "Request too large.")
            return None
        try:
            args = json.loads(self.rfile.read(length) or b"[]")
        except ValueError:
            args = None
        if not isinstance(args, list):
            self._json(400, {"ok": False, "error": "Body must be a JSON array."})
            return None
        return args

    def _content_length(self) -> int:
        """Content-Length as an int, or -1 when it is not a number."""
        try:
            return int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return -1

    def _discard_body(self) -> None:
        # Unread bytes would be parsed as the next request on a kept-alive
        # socket, and closing with bytes unread resets the connection on
        # Windows, so the browser would lose the reply.
        length = self._content_length()
        if 0 <= length <= MAX_BODY_BYTES:
            self.rfile.read(length)
        else:
            self.close_connection = True

    def _refuse(self, status: int, message: str) -> None:
        self._discard_body()
        self._json(status, {"ok": False, "error": message})

    def _index(self) -> None:
        html = (self.server.ui_dir / "index.html").read_text(encoding="utf-8")
        tag = f'<meta name="sori-token" content="{self.server.token}">\n'
        self._send(200, CONTENT_TYPES[".html"], html.replace("</head>", tag + "</head>", 1).encode("utf-8"))

    def _static(self, url_path: str) -> None:
        root = self.server.ui_dir.resolve()
        try:
            target = (root / url_path.lstrip("/")).resolve()
            target.relative_to(root)
            is_file = target.is_file()
        except (ValueError, OSError):
            is_file = False
        if not is_file:
            self._json(404, {"ok": False, "error": "Not found."})
            return
        content_type = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self._send(200, content_type, target.read_bytes())

    def _events(self, query: str) -> None:
        if not self._token_ok(parse_qs(query).get("token", [""])[0]):
            self._json(403, {"ok": False, "error": "Not allowed."})
            return
        client = self.server.hub.subscribe()
        self.close_connection = True
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self._security_headers()
            self.end_headers()
            self._write(b"retry: 2000\n\n")
            while True:
                try:
                    message = client.get(timeout=KEEPALIVE_SECONDS)
                except queue.Empty:
                    self._write(b": keepalive\n\n")
                    continue
                if message is None:
                    return
                self._write(f"data: {message}\n\n".encode())
        except OSError:
            log.debug("event stream closed by the browser")
        finally:
            self.server.hub.unsubscribe(client)

    # -- replies ------------------------------------------------------------

    def _write(self, data: bytes) -> None:
        self.wfile.write(data)
        self.wfile.flush()

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, "application/json", json.dumps(payload, default=str).encode("utf-8"))


class SoriServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR would let a second process bind the same port,
    # and a second launch would then never find the running copy.
    allow_reuse_address = os.name != "nt"
    daemon_threads = True
    block_on_close = False
    request_queue_size = 64

    def __init__(self, api: Any, ui_dir: Path, home: Path, hub: EventHub, port: int) -> None:
        self.token = secrets.token_urlsafe(32)
        self.ui_dir = ui_dir
        self.home_id = home_id(home)
        self.hub = hub
        self.methods = bridge_methods(api)
        super().__init__((HOST, port), Handler)
        bound = self.server_address[1]
        self.allowed_hosts = {f"{HOST}:{bound}", f"localhost:{bound}"}

    def server_bind(self) -> None:
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        # HTTPServer.server_bind also calls getfqdn, which can stall for seconds on Windows.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def handle_error(self, request: Any, client_address: Any) -> None:
        log.debug("connection ended abruptly", exc_info=True)


def bridge_methods(api: Any) -> dict[str, Callable[..., Any]]:
    """The Api methods a page may call: only those marked by app.bridge."""
    methods = {}
    for name in dir(type(api)):
        if not name.startswith("_") and getattr(getattr(type(api), name), "is_bridge_method", False):
            methods[name] = getattr(api, name)
    return methods


def url_for(port: int) -> str:
    return f"http://{HOST}:{port}/"


BUSY_MESSAGE = (
    "Sori is already working in this folder: a sweep or the desktop window is running. "
    "Wait for it to finish, or close it, then start Sori again."
)
PORT_MESSAGE = (
    "Sori could not open port {port}. If you just stopped Sori, wait a moment and try again. "
    "If another program uses the port, set SORI_PORT to a different number."
)


def run(
    api: Any,
    ui_dir: Path,
    home: Path,
    start_engine: Callable[[], None],
    open_browser: bool = True,
    port: int | None = None,
) -> int:
    """Serve until Stop is pressed. A second launch just opens the running copy."""
    port = configured_port() if port is None else port
    hub = EventHub()
    lock = EngineLock(home)
    locked = lock.acquire()
    try:
        server = SoriServer(api, ui_dir, home, hub, port) if locked else None
    except OSError:
        server = None
    if server is None:
        lock.release()
        if is_running(port, home):
            if open_browser:
                webbrowser.open(url_for(port))
            return 0
        _tell_user(BUSY_MESSAGE if not locked else PORT_MESSAGE.format(port=port))
        return 1

    api._attach_event_sink(hub.publish)
    start_engine()
    if open_browser:
        webbrowser.open(url_for(server.server_address[1]))
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        log.info("stopped from the keyboard")
    finally:
        hub.close()
        server.server_close()
        lock.release()
    return 0


def _tell_user(message: str) -> None:
    """Show a startup failure: the windowed exe has no console to print to."""
    log.error(message)
    if os.name == "nt":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
    else:
        print(message)


# ---------------------------------------------------------------------------
# File pickers
# ---------------------------------------------------------------------------
#
# A browser never reveals a real local path, and Sori needs one. The server is
# on the user's own desktop, so it can open the Windows dialogs itself. An
# invisible TopMost owner keeps the dialog above the browser window. It has to
# be shown for that to work, or the dialog can open behind the browser.

MEDIA_PATTERNS = ";".join(("*.mp3", "*.m4a", "*.wav", "*.mp4"))
MEDIA_LABEL = f"Audio and video ({MEDIA_PATTERNS})"

_PICKER_SETUP = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "Add-Type -AssemblyName System.Windows.Forms; "
    "$owner = New-Object System.Windows.Forms.Form; "
    "$owner.TopMost = $true; "
    "$owner.ShowInTaskbar = $false; "
    "$owner.Opacity = 0; "
    "$owner.StartPosition = 'CenterScreen'; "
    "$owner.Show(); "
    "$owner.Activate(); "
)
_FOLDER_SCRIPT = _PICKER_SETUP + (
    "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
    "$d.Description = 'Choose where Sori saves transcripts'; "
    "if ($d.ShowDialog($owner) -eq 'OK') { $d.SelectedPath }"
)
_FILES_SCRIPT = _PICKER_SETUP + (
    "$d = New-Object System.Windows.Forms.OpenFileDialog; "
    "$d.Title = 'Choose audio or video for Sori'; "
    "$d.Multiselect = $true; "
    f"$d.Filter = '{MEDIA_LABEL}|{MEDIA_PATTERNS}|All files (*.*)|*.*'; "
    "if ($d.ShowDialog($owner) -eq 'OK') { $d.FileNames }"
)


def _run_picker(script: str) -> list[str]:
    if os.name != "nt":
        raise RuntimeError("File pickers need Windows. Type the path instead.")
    root = os.environ.get("SystemRoot", r"C:\Windows")
    powershell = str(Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")
    result = subprocess.run(  # noqa: S603 - fixed program, fixed script
        [powershell, "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        log.error("file picker failed: %s", result.stderr.decode("utf-8", "replace"))
        raise RuntimeError("Windows couldn't open the file picker.")
    return [line.strip() for line in result.stdout.decode("utf-8-sig").splitlines() if line.strip()]


def pick_folder() -> str | None:
    picked = _run_picker(_FOLDER_SCRIPT)
    return picked[0] if picked else None


def pick_files() -> list[str]:
    return _run_picker(_FILES_SCRIPT)
