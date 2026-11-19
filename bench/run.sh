#!/bin/sh
# Re-run the design-stage benchmarks that work offline, and print each measured value next to the recorded one.
# Usage, from the repository root:  ./bench/run.sh [--full] [--only NAME[,NAME...]] [--out DIR]
# Needs Python 3 (tested with 3.14.4); standard library only; no network; nothing outside this checkout is written.
set -eu
cd "$(dirname "$0")/.."
exec python3 -I -B -X utf8 bench/run.py "$@"
