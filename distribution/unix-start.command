#!/bin/sh
cd "$(dirname "$0")/app" || exit 1
exec sh ./start-sori.command "$@"
