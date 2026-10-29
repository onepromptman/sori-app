#!/usr/bin/env python3
"""
shows.py — subscriptions and folders from a shell, no window needed.

The same add / remove / auto / folder actions the Sori window offers, exposed
as a command so they can be driven from a script or a Claude Code / Cowork
skill. Nothing here is new logic: every verb calls app.Api (the bridge the
window uses) and reads and writes the same shows.json, so the exe shows what
the CLI did and the CLI lists what the exe added. Honours SORI_HOME.

    py shows.py list [--json]
    py shows.py add <url> [--auto] [--auto-train] [--folder <folder>] [--json]
    py shows.py remove <show>
    py shows.py auto <show> on|off
    py shows.py auto-train <show> on|off
    py shows.py folder list | add <name> | rename <folder> <name>
                       | remove <folder> | set <show> <folder>
    py shows.py check [--json]        poll every feed, list new episodes (network)

<show> and <folder> take an id or an exact name (case-insensitive); a name
two shows share is an error, so use the id from `list`. `add` fetches the
feed; a "you already follow this show" warning goes to stderr and is not a
failure. Exit codes: 0 ok, 1 the engine refused (message on stderr, "!! "),
2 usage.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys

import app
import sori_log


class CliError(Exception):
    """A refusal to report as `!! message` with exit 1."""


def _call(method, *args):
    """Run one bridge method quietly and unwrap {ok, data|error}.

    `bridge` prints a traceback to stderr on every refusal and deck_render
    prints a warning on import; neither belongs in CLI output, so both
    streams are swallowed for the duration of the call.
    """
    sink = io.StringIO()
    with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
        res = method(*args)
    if not res.get("ok"):
        raise CliError(res.get("error") or "unknown error")
    return res.get("data")


def _resolve(items: list[dict], ref: str, what: str) -> str:
    """Id-or-name lookup: exact id wins; else case-insensitive exact name."""
    ref = (ref or "").strip()
    for it in items:
        if it.get("id") == ref:
            return it["id"]
    hits = [it for it in items if (it.get("name") or "").strip().lower() == ref.lower()]
    if len(hits) == 1:
        return hits[0]["id"]
    if not hits:
        raise CliError(f"no {what} matches {ref!r} (use an id from `list`)")
    ids = ", ".join(h["id"] for h in hits)
    raise CliError(f"{ref!r} names {len(hits)} {what}s ({ids}); use the id")


def _show_id(api: app.Api, ref: str) -> str:
    return _resolve(_call(api.list_shows), ref, "show")


def _folder_id(api: app.Api, ref: str) -> str:
    return _resolve(_call(api.list_folders), ref, "folder")


def _emit(data, as_json: bool, human) -> None:
    if as_json:
        # ensure_ascii stays on: json escapes non-ASCII itself, so the output
        # is valid JSON on any console (backslashreplace would not be).
        print(json.dumps(data, indent=2))
    else:
        human(data)


def _table(rows: list[list[str]], header: list[str]) -> None:
    widths = [max(len(str(r[i])) for r in [header, *rows]) for i in range(len(header))]
    for r in [header, *rows]:
        print("  ".join(str(c).ljust(w) for c, w in zip(r, widths)).rstrip())


# -- verbs ------------------------------------------------------------------


def cmd_list(api: app.Api, args) -> int:
    shows = _call(api.list_shows)
    folders = {f["id"]: f["name"] for f in _call(api.list_folders)}

    def human(rows):
        if not rows:
            print("no shows yet. add one: py shows.py add <feed url or YouTube channel>")
            return
        _table(
            [
                [
                    s["id"],
                    s["name"],
                    s["type"],
                    "on" if s["auto"] else "off",
                    "on" if s.get("auto_train") else "off",
                    folders.get(s.get("folder"), s.get("folder") or ""),
                    (s.get("last_checked") or "never")[:19],
                ]
                for s in rows
            ],
            ["id", "name", "type", "auto", "auto-train", "folder", "last checked"],
        )

    _emit(shows, args.json, human)
    return 0


def cmd_add(api: app.Api, args) -> int:
    folder_id = _folder_id(api, args.folder) if args.folder else None
    show = _call(api.add_show, args.url)
    warning = show.pop("warning", None)
    if args.auto:
        show["auto"] = _call(api.set_auto, show["id"], True)["auto"]
    if args.auto_train:
        show["auto_train"] = _call(api.set_auto_train, show["id"], True)["auto_train"]
    if folder_id:
        show["folder"] = _call(api.set_show_folder, show["id"], folder_id)["folder"]
    if warning:
        print(f"warning: {warning}", file=sys.stderr)

    def human(s):
        flags = [k for k in ("auto", "auto_train") if s.get(k)]
        suffix = f", {', '.join(flags)}" if flags else ""
        print(f"added {s['id']}  {s['name']}  ({s['type']}{suffix})")

    _emit(show, args.json, human)
    return 0


def cmd_remove(api: app.Api, args) -> int:
    sid = _show_id(api, args.show)
    _call(api.remove_show, sid)
    print(f"removed {sid}")
    return 0


def cmd_auto(api: app.Api, args) -> int:
    sid = _show_id(api, args.show)
    res = _call(api.set_auto, sid, args.state == "on")
    print(f"{sid} auto {'on' if res['auto'] else 'off'}")
    return 0


def cmd_auto_train(api: app.Api, args) -> int:
    sid = _show_id(api, args.show)
    res = _call(api.set_auto_train, sid, args.state == "on")
    print(f"{sid} auto-train {'on' if res['auto_train'] else 'off'}")
    return 0


def cmd_folder(api: app.Api, args) -> int:
    sub = args.folder_cmd
    if sub == "list":
        folders = _call(api.list_folders)
        counts: dict[str, int] = {}
        for s in _call(api.list_shows):
            counts[s.get("folder")] = counts.get(s.get("folder"), 0) + 1
        _table([[f["id"], f["name"], str(counts.get(f["id"], 0))] for f in folders], ["id", "name", "shows"])
        return 0
    if sub == "add":
        f = _call(api.add_folder, args.name)
        print(f"added folder {f['id']}  {f['name']}")
        return 0
    if sub == "rename":
        f = _call(api.rename_folder, _folder_id(api, args.folder), args.name)
        print(f"renamed {f['id']} to {f['name']}")
        return 0
    if sub == "remove":
        fid = _folder_id(api, args.folder)
        _call(api.remove_folder, fid)
        print(f"removed folder {fid} (its shows moved to Unsorted)")
        return 0
    if sub == "set":
        sid = _show_id(api, args.show)
        fid = _folder_id(api, args.folder)
        _call(api.set_show_folder, sid, fid)
        print(f"{sid} -> folder {fid}")
        return 0
    raise CliError(f"unknown folder command {sub!r}")


def cmd_check(api: app.Api, args) -> int:
    res = app.check_all()  # plain function, not bridge-wrapped

    def human(r):
        eps = r["episodes"]
        print(f"checked {r['show_count']} show(s), {len(eps)} new episode(s)")
        by_show: dict[str, list[dict]] = {}
        for e in eps:
            by_show.setdefault(e["show_name"], []).append(e)
        for name, items in by_show.items():
            print(f"  {name}")
            for e in items:
                print(f"    {e.get('date') or '----------'}  {e.get('title', '')}")
        for err in r["errors"]:
            print(f"  !! {err['show']}: {err['error']}", file=sys.stderr)

    _emit(res, args.json, human)
    return 0


# -- argparse ---------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="shows.py", description="Sori subscriptions from the shell (same store as the window)."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="list subscriptions")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("add", help="subscribe to an RSS feed or YouTube channel (fetches the feed)")
    s.add_argument("url")
    s.add_argument("--auto", action="store_true", help="transcribe new episodes automatically")
    s.add_argument("--auto-train", action="store_true", help="also generate trainings (paid)")
    s.add_argument("--folder", help="folder id or name")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("remove", help="unsubscribe")
    s.add_argument("show", help="show id or exact name")
    s.set_defaults(fn=cmd_remove)

    for name, fn in (("auto", cmd_auto), ("auto-train", cmd_auto_train)):
        s = sub.add_parser(name, help=f"turn {name} on or off for a show")
        s.add_argument("show", help="show id or exact name")
        s.add_argument("state", choices=("on", "off"))
        s.set_defaults(fn=fn)

    f = sub.add_parser("folder", help="source folders")
    fsub = f.add_subparsers(dest="folder_cmd", required=True)
    fsub.add_parser("list")
    x = fsub.add_parser("add")
    x.add_argument("name")
    x = fsub.add_parser("rename")
    x.add_argument("folder", help="folder id or exact name")
    x.add_argument("name")
    x = fsub.add_parser("remove")
    x.add_argument("folder", help="folder id or exact name")
    x = fsub.add_parser("set", help="move a show into a folder")
    x.add_argument("show", help="show id or exact name")
    x.add_argument("folder", help="folder id or exact name")
    f.set_defaults(fn=cmd_folder)

    s = sub.add_parser("check", help="poll every feed and list new episodes (network)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_check)
    return p


def _tolerant_streams() -> None:
    """A piped stdout on Windows is cp1252 + strict; a Korean show name must
    not turn into a UnicodeEncodeError traceback. Escape instead."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    _tolerant_streams()
    sori_log.setup()
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:  # argparse: 2 on usage error, 0 on --help
        return int(exc.code or 0)
    try:
        return args.fn(app.Api(), args)
    except CliError as exc:
        print(f"!! {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
