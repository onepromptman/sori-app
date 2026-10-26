# cloud/ — the captions-only cloud sweep

Everything Sori needs to run as a scheduled cloud routine (a Claude Code
`/schedule` routine, see `ROUTINE.md`) instead of on Bryan's PC. The cloud
runner has no GPU and no Whisper: it installs `requirements-captions.txt`,
so only **YouTube shows** (captions via yt-dlp) can be swept there. With an
`ANTHROPIC_API_KEY` it can also generate training decks for shows marked
auto-train (paid; see the spend gate in `ROUTINE.md`).

| File | Role |
|---|---|
| `sweep_cloud.sh` | The one command the routine runs: guard, `app.py --sweep`, commit + push the output repo. `--dry-run` skips the push. |
| `guard.py` | Exits 3 if any show in the cloud `shows.json` is not `type: youtube`. Dependency-free. |
| `ROUTINE.md` | The routine prompt, secrets, schedule, dry-run procedure, and what Bryan must confirm first. |

Nothing in this folder creates the routine or the output repo. Both are
ask-first.

## The output repo: `onepromptman/sori-output` (private)

**Decision 2 of the v3.2 handoff, recommended and not yet confirmed by
Bryan.** The alternative was Google Drive via connector. Until he confirms,
this layout is a proposal; the script works against any checkout path.

`sweep_cloud.sh` sets `SORI_HOME=$SORI_OUTPUT_DIR/state`, and Sori keeps all
of its state under `SORI_HOME`, so everything lands under `state/`:

```
sori-output/
  .gitignore              state/credentials.json, state/*.json.tmp, state/*.json.bad
  README.md               one paragraph: "written by the Sori cloud routine, do not edit by hand"
  state/
    shows.json            the CLOUD subscription list + per-show `seen` markers
    Transcripts/<Show>/<date> - <title>.txt  (+ .json segment sidecar)
    Trainings/<Show>/<date> - <title>.pptx   (+ matching .md study guide)
    sweep.log             append-only log; one block per run, the newest last
```

Notes on that layout:

- `state/shows.json` is **separate from Bryan's desktop `shows.json`**. It is
  the cloud's own subscription list; edit it with
  `SORI_HOME=/path/to/sori-output/state py shows.py add <youtube url> --auto`
  from a Sori checkout, commit, push. Only YouTube shows; `guard.py` refuses
  anything else. `add_show` seeds `seen` with all but the newest video, so a
  freshly added channel yields exactly one transcript on the next run.
- `Transcripts/` and `Trainings/` sit under `state/` because
  `transcripts_dir()` defaults to `state_dir()/Transcripts`. Do not expect
  them at the repo root.
- `check_all()` rewrites `last_checked` and the sweep appends to `sweep.log`
  on every run, so **every real run produces a commit** even when nothing
  new was transcribed. The commit message carries the counts:
  `sweep 2026-09-05T16:03:00Z: 1 transcribed, 0 trained`.
- `state/credentials.json` must never exist in this repo. The script refuses
  to commit if the file exists and is not gitignored (exit 4). The API key
  reaches the engine only through the `ANTHROPIC_API_KEY` environment
  variable (see the open item below).

## Running it by hand (from a Sori checkout)

```bash
SORI_OUTPUT_DIR=/path/to/sori-output bash cloud/sweep_cloud.sh --dry-run   # no push
SORI_OUTPUT_DIR=/path/to/sori-output bash cloud/sweep_cloud.sh             # push
```

`PY` defaults to `py`, then `python3` if `py` is absent. Exit codes: 0 ok
(including "no shows" and "no changes"), 2 usage, 3 guard refused a
non-YouTube show, 4 credentials file at risk of being committed; anything
else is the sweep or git failing under `set -e`.

## The key in the cloud (shipped in 3.3)

`app.anthropic_api_key()` reads `ANTHROPIC_API_KEY` from the environment
only when `SORI_KEY_FROM_ENV=1` is also set. `sweep_cloud.sh` exports that
opt-in when a key is present and nothing else does, so the desktop's
scheduled sweep over Bryan's real shows still spends only on a key saved in
Settings. The key never touches the output repo: no `credentials.json` is
written in the cloud (and the script refuses to commit one, exit 4).

## Network: what the cloud runner can reach

Anthropic-hosted environments default to **Trusted** network access
(package registries and GitHub). Probed from a cloud session on
2026-10-26, `youtube.com`, `feeds.simplecast.com` and a podcast CDN all
returned `403` from the egress proxy. The routine therefore needs an
environment with **Custom** network access listing at least:

```
*.youtube.com
*.googlevideo.com
*.ytimg.com
www.google.com
```

plus "Also include default list of common package managers" so
`requirements-captions.txt` still installs. Even then YouTube answers many
datacenter IPs with "Sign in to confirm you're not a bot", and yt-dlp's
proof-of-origin workaround no longer reliably clears it. Treat the cloud
sweep as best-effort: a bot-checked video fails cleanly, is retried on the
next two runs, then parks for the desktop or the Claude door to pick up.
