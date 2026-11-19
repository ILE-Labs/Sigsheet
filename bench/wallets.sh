#!/bin/sh
# Optional: clone ckb-cli, CCC and Neuron at their pinned commits (only if missing from refs/), check that each
# design-stage diff applies, and count it. Usage, from the repository root:  ./bench/wallets.sh [--refs DIR]
set -eu
cd "$(dirname "$0")/.."
exec python3 -I -B -X utf8 bench/wallets.py "$@"
