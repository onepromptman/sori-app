#!/bin/sh
cd "$(dirname "$0")" || exit 1
export SORI_PROFILE=portable
export SORI_WHISPER_BACKEND=faster
printf '%s\n' 'Sori opens in your browser. Leave this window open while using Sori.'
exec ./runtime/bin/python3.12 -E -s -B ./app/app.py "$@"
