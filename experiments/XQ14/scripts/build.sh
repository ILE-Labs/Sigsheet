#!/bin/sh
# Build the Nervos app (8c50034) for the Nano S Plus (SDK target nanos2) with SDK v26.6.1.
set -eu
L=$(cd "$(dirname "$0")/.." && pwd)
export PATH="$L/venv/bin:$L/bin:/usr/lib/llvm-21/bin:$PATH"
cd "$L/app-work/app-nervos-8c50034"
make -j2 BOLOS_SDK="$L/ledger-secure-sdk" TARGET=nanos2 SYSROOT="$L/sysroot" "$@"
