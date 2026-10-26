#!/usr/bin/env bash
# Captions-only Sori sweep for a cloud routine (see cloud/ROUTINE.md).
#
#   SORI_OUTPUT_DIR=/path/to/sori-output [ANTHROPIC_API_KEY=...] \
#     bash cloud/sweep_cloud.sh [--dry-run]
#
# - SORI_HOME becomes $SORI_OUTPUT_DIR/state, so shows.json, Transcripts/,
#   Trainings/ and sweep.log all live inside the output repo.
# - cloud/guard.py refuses to run if any subscribed show is not a YouTube
#   show (this profile has no Whisper).
# - ANTHROPIC_API_KEY is optional and stays in the environment; this script
#   never prints or copies it. app.anthropic_api_key() reads the environment
#   only when SORI_KEY_FROM_ENV=1, which this script exports when a key is
#   present, so the cloud sweep can train auto-train shows (paid, one call per
#   new video) without a credentials.json ever existing in the output repo.
#   The desktop sweep never sets the opt-in, so a stray shell key there spends
#   nothing.
# - --dry-run does everything except `git push`.
set -euo pipefail

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "!! unknown argument: $arg" >&2; exit 2 ;;
  esac
done

: "${SORI_OUTPUT_DIR:?set SORI_OUTPUT_DIR to a checkout of the sori-output repo}"
if [ ! -d "$SORI_OUTPUT_DIR" ]; then
  echo "!! SORI_OUTPUT_DIR does not exist: $SORI_OUTPUT_DIR" >&2
  exit 2
fi

SORI_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export SORI_HOME="$SORI_OUTPUT_DIR/state"
mkdir -p "$SORI_HOME"

# `py` on Windows, python3 elsewhere; PY overrides both.
PY="${PY:-py}"
if ! command -v "$PY" >/dev/null 2>&1; then
  PY=python3
fi

echo "sori root:   $SORI_ROOT"
echo "output repo: $SORI_OUTPUT_DIR"
echo "state:       $SORI_HOME"
echo "python:      $PY"
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  export SORI_KEY_FROM_ENV=1
  echo "api key:     present in env; auto-train shows WILL make a paid Claude call per new video"
else
  echo "api key:     not set (auto-train shows will log 'training failed', nothing spent)"
fi

# 1. Captions-only guard (exit 3 on a non-YouTube show).
"$PY" "$SORI_ROOT/cloud/guard.py"

# 2. The sweep itself. sweep() writes its own block to $SORI_HOME/sweep.log.
(cd "$SORI_ROOT" && "$PY" app.py --sweep)

# 3. Counts from the last sweep block (selftest blocks share the file, so
#    anchor on the sweep header). A run with zero shows has no "Done" line.
LOG="$SORI_HOME/sweep.log"
TRANSCRIBED=0
TRAINED=0
if [ -f "$LOG" ]; then
  BLOCK="$(awk '/^=== .* sweep /{buf=""} {buf=buf $0 "\n"} END{printf "%s", buf}' "$LOG")"
  n="$(printf '%s' "$BLOCK" | grep -oE '[0-9]+ transcribed' | tail -n1 | grep -oE '^[0-9]+' || true)"
  m="$(printf '%s' "$BLOCK" | grep -oE '[0-9]+ trained,' | tail -n1 | grep -oE '^[0-9]+' || true)"
  TRANSCRIBED="${n:-0}"
  TRAINED="${m:-0}"
fi
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
MSG="sweep $STAMP: $TRANSCRIBED transcribed, $TRAINED trained"
echo "summary:     $MSG"

# 4. Commit and push the output repo, only if it is one and something changed.
if ! git -C "$SORI_OUTPUT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "not a git repo: nothing committed, nothing pushed"
  exit 0
fi
# Never let a credentials file ride along, even if .gitignore is missing.
if [ -e "$SORI_HOME/credentials.json" ] && \
   ! git -C "$SORI_OUTPUT_DIR" check-ignore -q state/credentials.json; then
  echo "!! state/credentials.json exists and is not gitignored; refusing to commit" >&2
  exit 4
fi
if [ -z "$(git -C "$SORI_OUTPUT_DIR" status --porcelain)" ]; then
  echo "no changes: nothing committed, nothing pushed"
  exit 0
fi
git -C "$SORI_OUTPUT_DIR" add -A -- state
git -C "$SORI_OUTPUT_DIR" commit -q -m "$MSG"
echo "committed:   $MSG"
if [ "$DRY_RUN" -eq 1 ]; then
  echo "dry run:     push skipped"
  exit 0
fi
git -C "$SORI_OUTPUT_DIR" push -q
echo "pushed"
