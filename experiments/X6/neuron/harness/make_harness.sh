#!/bin/sh
# Rebuild the Neuron test harness tests/x6/x6-sigsheet.test.ts inside a patched Neuron wallet package
# (Neuron v0.204.1, d3a7467d218e4b6f777326682a83fec802669c00, with ../patch.diff applied): lines 1-193 of
# Neuron's own tests/services/tx/transaction-sender.test.ts, then this experiment's changes in
# x6-sigsheet.test.diff.
# Usage, from experiments/X6/neuron/harness:  sh make_harness.sh <path to packages/neuron-wallet>
set -eu
out="$1/tests/x6/x6-sigsheet.test.ts"
mkdir -p "$(dirname "$out")"
sed -n '1,193p' "$1/tests/services/tx/transaction-sender.test.ts" > "$out"
patch -s "$out" < x6-sigsheet.test.diff
echo "wrote $out"
