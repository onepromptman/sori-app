# cloud/ - the captions-only cloud sweep

Everything Sori needs to run as a scheduled cloud routine (a Claude Code
`/schedule` routine, see `ROUTINE.md`) instead of on your own PC. The cloud
runner has no GPU and no Whisper: it installs `requirements-captions.txt`,
so only **YouTube shows** (captions via yt-dlp) can be swept there. Cloud
auto-training is blocked because the sweep does not read `ANTHROPIC_API_KEY`;
see the open item and spend gate in `ROUTINE.md`.

| File | Role |
|---|---|
| `sweep_cloud.sh` | The one command the routine runs: guard, `app.py --sweep`, commit + push the output repo. `--dry-run` skips the push. |
| `guard.py` | Exits 3 if any show in the cloud `shows.json` is not `type: youtube`. Dependency-free. |
| `ROUTINE.md` | The routine prompt, secrets, schedule, dry-run procedure, and what the owner must confirm first. |

Nothing in this folder creates the routine or the output repo. Both are
ask-first.

## The output repo: `<owner>/sori-output` (private)

**Design note: this destination is recommended and not yet confirmed by
the owner.** The alternative was Google Drive via connector. Until it is confirmed,
this layout is a proposal; the script works against any checkout path.

`sweep_cloud.sh` sets `SORI_HOME=$SORI_OUTPUT_DIR/state`, and Sori keeps all
of its state under `SORI_HOME`, so everything lands under `state/`:

```
sori-output/
  .gitignore              state/credentials.json, state/*.json.tmp, state/*.json.bad*
  README.md               one paragraph: "written by the Sori cloud routine, do not edit by hand"
  state/
    shows.json            the CLOUD subscription list + per-show `seen` markers
    Transcripts/<Show>/<date> - <title>.txt  (+ .json segment sidecar)
    Trainings/<Show>/<date> - <title>.pptx   (+ matching .md study guide)
    sweep.log             append-only log; one block per run, the newest last
```

Notes on that layout:

- `state/shows.json` is **separate from your desktop `shows.json`**. It is
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
  to commit if the file exists and is not gitignored (exit 4). It also refuses
  unignored corrupt-store backups, including numbered backups. The API key
  reaches the engine through the `ANTHROPIC_API_KEY` environment variable only
  when `SORI_KEY_FROM_ENV=1` is set. The cloud wrapper sets that opt-in when a key exists.

## Running it by hand (from a Sori checkout)

```bash
SORI_OUTPUT_DIR=/path/to/sori-output bash cloud/sweep_cloud.sh --dry-run   # no push
SORI_OUTPUT_DIR=/path/to/sori-output bash cloud/sweep_cloud.sh             # push
```

`PY` defaults to `py`, then `python3` if `py` is absent. Exit codes: 0 ok
(including "no shows" and "no changes"), 2 usage, 3 guard refused a
non-YouTube show, 4 credentials file at risk of being committed; anything
else is the sweep or git failing under `set -e`.

## Before the paid run

The cloud wrapper explicitly enables SORI_KEY_FROM_ENV=1 when an environment
key is present. Only shows with auto_train enabled can use it. Ordinary browser
startup does not set the opt-in. A saved key takes precedence over the environment.

This route has unit coverage, but no live paid cloud acceptance test. Obtain
authorization for the intended transcript sharing and API spend before enabling
auto-training. The --dry-run flag suppresses Git push; it does not suppress model
calls. For a no-spend test, omit the key and disable auto_train.
