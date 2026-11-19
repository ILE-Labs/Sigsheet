#!/bin/sh
# Optional: fetch the public mainnet inputs (CKB mainnet JSON-RPC and GitHub, read-only, pinned) and rebuild the
# mainnet case files, so that ./bench/run.sh also runs the real cases. See experiments/mainnet-inputs.md.
# Usage, from the repository root:  ./bench/fetch-mainnet.sh [--rpc URL] [--comments-only] [--no-build]
set -eu
cd "$(dirname "$0")/.."
exec python3 -I -B -X utf8 bench/fetch_mainnet.py "$@"
