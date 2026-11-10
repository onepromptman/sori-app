"""The local web server: who may call it, what it serves, and the single-instance lock.

Each test runs a real server on a free port against a real ``Api`` whose workers
and poller are never started, so nothing transcribes or touches the network.
"""

from __future__ import annotations

import http.client
import json
import re
import socket
import threading
import types
from pathlib import Path

import pytest

import app
import webserver
from engine_lock import EngineLock

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def server(sori_home):
    api = app.Api()
    srv = webserver.SoriServer(api, ROOT / "ui", sori_home, webserver.EventHub(), 0)
    api._attach_event_sink(srv.hub.publish)
    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def request(srv, method, path, body=None, headers=None, host=None, auth=False):
    port = srv.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    sent = dict(headers or {})
    sent["Host"] = host or f"127.0.0.1:{port}"
    if auth:
        sent["X-Sori-Token"] = srv.token
    conn.request(method, path, body=body, headers=sent)
    reply = conn.getresponse()
    data = reply.read()
    conn.close()
    return reply, data


def call(srv, method, *args):
    reply, data = request(srv, "POST", f"/api/{method}", json.dumps(args), auth=True)
    assert reply.status == 200
    return json.loads(data)


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def fake_powershell(monkeypatch, returncode=0, stdout=b"", stderr=b""):
    done = types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
    monkeypatch.setattr(webserver.os, "name", "nt")
    monkeypatch.setattr(webserver.subprocess, "run", lambda *a, **k: done)
    monkeypatch.setattr(webserver.subprocess, "CREATE_NO_WINDOW", 0, raising=False)


# -- who may call it --------------------------------------------------------


def test_page_carries_the_token(server):
    reply, data = request(server, "GET", "/")
    assert reply.status == 200
    assert f'<meta name="sori-token" content="{server.token}">'.encode() in data
    assert "script-src 'self'" in reply.getheader("Content-Security-Policy")


@pytest.mark.parametrize("origin", ["https://outside.example", "null"])
def test_foreign_origin_is_refused_even_with_token(server, origin):
    reply, _ = request(server, "POST", "/api/list_shows", "[]", {"Origin": origin}, auth=True)
    assert reply.status == 403


def test_same_origin_is_allowed(server):
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    reply, _ = request(server, "POST", "/api/list_shows", "[]", {"Origin": origin}, auth=True)
    assert reply.status == 200


@pytest.mark.parametrize("sent", [None, "wrong", "caf\u00e9"])
def test_api_refuses_a_missing_or_wrong_token(server, sent):
    headers = {} if sent is None else {"X-Sori-Token": sent.encode("latin-1")}
    reply, _ = request(server, "POST", "/api/list_shows", "[]", headers)
    assert reply.status == 403


@pytest.mark.parametrize("method,path", [("GET", "/"), ("GET", "/app.js"), ("POST", "/api/list_shows")])
def test_a_foreign_host_is_refused(server, method, path):
    is_post = method == "POST"
    reply, data = request(server, method, path, "[]" if is_post else None, host="evil.example", auth=is_post)
    assert reply.status == 403
    assert server.token.encode() not in data


def test_quit_needs_the_token(server):
    reply, _ = request(server, "POST", "/quit", "[]")
    assert reply.status == 403


def test_no_response_allows_other_origins(server):
    reply, _ = request(server, "GET", "/", headers={"Origin": "https://evil.example"})
    assert reply.getheader("Access-Control-Allow-Origin") is None
    assert reply.getheader("X-Frame-Options") == "DENY"


# -- the bridge -------------------------------------------------------------


def test_a_bridge_call_round_trips(server):
    assert call(server, "list_shows") == {"ok": True, "data": []}


def test_arguments_reach_the_method_and_state_is_saved(server):
    created = call(server, "add_folder", "Talks")
    assert created["ok"] is True
    assert "Talks" in [folder["name"] for folder in call(server, "list_folders")["data"]]


def test_engine_errors_come_back_as_ok_false(server):
    result = call(server, "remove_show", "no-such-show")
    assert result["ok"] is False
    assert result["error"]


def test_only_public_bridge_methods_are_exposed():
    class Fake:
        @app.bridge
        def allowed(self):
            return 1

        @app.bridge
        def _private(self):
            return 2

        def helper(self):
            return 3

    assert list(webserver.bridge_methods(Fake())) == ["allowed"]


def test_the_real_api_exposes_the_ui_calls(server):
    assert {"list_shows", "transcribe_episode", "get_training_settings"} <= set(server.methods)


@pytest.mark.parametrize("name", ["_shutdown", "_emit", "__init__", "no_such_method"])
def test_private_and_unknown_methods_are_not_found(server, name):
    reply, _ = request(server, "POST", f"/api/{name}", "[]", auth=True)
    assert reply.status == 404


@pytest.mark.parametrize("body", ["{not json", '{"a": 1}', '"text"'])
def test_a_body_that_is_not_an_array_is_rejected(server, body):
    reply, _ = request(server, "POST", "/api/list_shows", body, auth=True)
    assert reply.status == 400


def test_an_oversized_body_is_rejected(server):
    port = server.server_address[1]
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", "/api/list_shows", skip_host=True)
    conn.putheader("Host", f"127.0.0.1:{port}")
    conn.putheader("X-Sori-Token", server.token)
    conn.putheader("Content-Length", str(webserver.MAX_BODY_BYTES + 1))
    conn.endheaders()
    assert conn.getresponse().status == 413
    conn.close()


# -- static files -----------------------------------------------------------


def test_scripts_are_served_with_a_script_type(server):
    reply, data = request(server, "GET", "/app.js")
    assert reply.status == 200
    assert reply.getheader("Content-Type").startswith("text/javascript")
    assert b"httpToken" in data


@pytest.mark.parametrize(
    "path",
    [
        "/../app.py",
        "/%2e%2e/app.py",
        "/..%5capp.py",
        "/fonts/../../app.py",
        "/C:/Windows/win.ini",
        "/nope.js",
        "/%00",
    ],
)
def test_only_files_under_ui_are_served(server, path):
    reply, data = request(server, "GET", path)
    assert reply.status == 404
    assert b"import webserver" not in data


# -- events -----------------------------------------------------------------


def test_events_reach_an_open_tab(server):
    port = server.server_address[1]
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(f"GET /events?token={server.token} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n".encode())
        received = b""
        while b"retry:" not in received:
            received += sock.recv(4096)
        server.hub.publish("job", {"id": "ep-1", "status": "done"})
        while b"ep-1" not in received:
            received += sock.recv(4096)
    assert b"HTTP/1.1 200" in received
    line = received.split(b"data: ", 1)[1].split(b"\n", 1)[0]
    assert json.loads(line) == {"name": "job", "payload": {"id": "ep-1", "status": "done"}}


def test_events_need_the_token(server):
    reply, _ = request(server, "GET", "/events?token=wrong")
    assert reply.status == 403


def test_engine_events_go_to_the_sink(sori_home):
    api = app.Api()
    seen = []
    api._attach_event_sink(lambda name, payload: seen.append((name, payload)))
    api._emit("queue", {"n": 1})
    assert seen == [("queue", {"n": 1})]


# -- single instance --------------------------------------------------------


def test_a_second_server_cannot_share_the_port(server, sori_home):
    with pytest.raises(OSError):
        webserver.SoriServer(
            app.Api(), ROOT / "ui", sori_home, webserver.EventHub(), server.server_address[1]
        )


def test_second_launch_opens_the_running_copy_without_a_second_engine(server, sori_home, monkeypatch):
    opened = []
    monkeypatch.setattr(webserver.webbrowser, "open", opened.append)
    started = []
    port = server.server_address[1]
    code = webserver.run(app.Api(), ROOT / "ui", sori_home, lambda: started.append(1), port=port)
    assert code == 0
    assert opened == [f"http://127.0.0.1:{port}/"]
    assert started == []


def test_a_port_held_by_something_else_is_reported_not_hijacked(sori_home, monkeypatch):
    told = []
    monkeypatch.setattr(webserver, "_tell_user", told.append)
    with socket.socket() as other:
        other.bind(("127.0.0.1", 0))
        other.listen()
        code = webserver.run(app.Api(), ROOT / "ui", sori_home, lambda: None, port=other.getsockname()[1])
    assert code == 1
    assert "SORI_PORT" in told[0]


def test_is_running_matches_the_state_folder(server, sori_home, tmp_path):
    port = server.server_address[1]
    assert webserver.is_running(port, sori_home) is True
    assert webserver.is_running(port, tmp_path / "other-home") is False


def test_is_running_is_false_when_nothing_listens():
    assert webserver.is_running(free_port(), Path("anywhere")) is False


def test_stop_ends_the_server(sori_home):
    port = free_port()
    ready = threading.Event()
    running = threading.Thread(
        target=webserver.run,
        args=(app.Api(), ROOT / "ui", sori_home, ready.set),
        kwargs={"open_browser": False, "port": port},
        daemon=True,
    )
    running.start()
    assert ready.wait(5)
    target = types.SimpleNamespace(server_address=("127.0.0.1", port))
    _, page = request(target, "GET", "/")
    token = re.search(rb'sori-token" content="([^"]+)"', page).group(1).decode()
    reply, _ = request(target, "POST", "/quit", "[]", {"X-Sori-Token": token})
    assert reply.status == 200
    running.join(5)
    assert not running.is_alive()


# -- what the engine does differently in browser mode -----------------------


def test_scheduled_sweep_stands_down_while_the_app_is_open(sori_home, monkeypatch):
    def must_not_run():
        raise AssertionError("the sweep checked feeds while the app was open")

    monkeypatch.setattr(app, "check_all", must_not_run)
    app.save_store({**app.load_store(), "shows": [{"id": "s", "name": "Show", "type": "rss"}]})
    with EngineLock(sori_home) as held:
        assert held
        assert app.sweep() == 0
    assert "already running" in (sori_home / "sweep.log").read_text(encoding="utf-8")


def test_choose_folder_uses_the_native_picker(sori_home, monkeypatch):
    picked = str(sori_home / "elsewhere")
    monkeypatch.setattr(webserver, "pick_folder", lambda: picked)
    result = app.Api().choose_folder()
    assert result["ok"] is True
    assert result["data"]["transcripts_dir"] == picked
    assert app.load_store()["settings"]["transcripts_dir"] == picked


def test_cancelling_the_folder_picker_changes_nothing(sori_home, monkeypatch):
    monkeypatch.setattr(webserver, "pick_folder", lambda: None)
    assert app.Api().choose_folder()["data"]["changed"] is False


def test_choose_files_queues_each_picked_file(sori_home, monkeypatch):
    monkeypatch.setattr(webserver, "pick_files", lambda: ["C:/a/one.mp3", "C:/a/two.wav"])
    api = app.Api()
    submitted = []
    monkeypatch.setattr(
        api._worker, "submit", lambda show, ep, settings, priority: submitted.append(ep["title"])
    )
    assert api.choose_files()["data"]["queued"] == ["C:/a/one.mp3", "C:/a/two.wav"]
    assert submitted == ["one", "two"]


def test_picker_reads_unicode_paths(monkeypatch):
    fake_powershell(monkeypatch, stdout="\ufeffC:\\오디오\\첫째.mp3\r\nC:\\오디오\\둘째.wav\r\n".encode())
    assert webserver.pick_files() == ["C:\\오디오\\첫째.mp3", "C:\\오디오\\둘째.wav"]


def test_a_failed_picker_says_so_plainly(monkeypatch):
    fake_powershell(monkeypatch, returncode=1, stderr=b"boom")
    with pytest.raises(RuntimeError, match="file picker"):
        webserver.pick_folder()


def test_file_picker_filter_is_well_formed():
    expected = "Audio and video (*.mp3;*.m4a;*.wav;*.mp4)|*.mp3;*.m4a;*.wav;*.mp4|All files (*.*)|*.*"
    assert f"$d.Filter = '{expected}'" in webserver._FILES_SCRIPT


def test_a_finished_episode_reports_done_once(sori_home):
    api = app.Api()
    statuses = []
    api._attach_event_sink(lambda name, payload: statuses.append(payload["status"]))
    report = api._worker._reporter("ep-1")
    report("transcribing", 0.5)
    report("done", 1.0)
    assert statuses == ["transcribing"]
