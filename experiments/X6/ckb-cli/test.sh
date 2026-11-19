#!/bin/sh
# Run ckb-cli's own tests in the copy, with the system's stable toolchain (not the clone's rust-toolchain pin, which
# would make rustup install 1.85.0 outside the repository), its own Cargo.lock, and the cargo cache in refs/.
# Usage, from the repository root: sh experiments/X6/ckb-cli/test.sh <log name>
set -u
INV=$(pwd)
cd experiments/X6/ckb-cli/src-copy
RUSTUP_TOOLCHAIN=stable CARGO_HOME=$INV/refs/_cargo-home cargo test --locked > ../results/$1.log 2>&1
echo "exit=$?" >> ../results/$1.log
