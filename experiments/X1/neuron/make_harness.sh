#!/bin/sh
# Rebuild the Neuron test harness tests/x1/x1-neuron.test.ts inside a Neuron checkout at tag v0.204.1
# (d3a7467d218e4b6f777326682a83fec802669c00): lines 1-193 of Neuron's own
# tests/services/tx/transaction-sender.test.ts, then this experiment's changes in x1-neuron.test.diff.
# Usage, from experiments/X1/neuron:  sh make_harness.sh <path to the Neuron checkout>
set -eu
out="$1/packages/neuron-wallet/tests/x1/x1-neuron.test.ts"
mkdir -p "$(dirname "$out")"
sed -n '1,193p' "$1/packages/neuron-wallet/tests/services/tx/transaction-sender.test.ts" > "$out"
patch -s "$out" < x1-neuron.test.diff
echo "wrote $out"
