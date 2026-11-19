#!/bin/sh
# Run Neuron's own tests for the modules the patch touches (and the whole wallet suite with "all"), in the copy.
# Usage, from the repository root: sh experiments/X6/neuron/test.sh <log name> [all]
set -u
# The Electron binary was never downloaded (X1 installed with --ignore-scripts). ELECTRON_OVERRIDE_DIST_PATH makes
# require('electron') return a path string instead of throwing; nothing is written anywhere.
cd experiments/X6/neuron/packages/neuron-wallet
FILES="tests/controllers/multisig.test.ts tests/controllers/hardware.test.ts tests/controllers/offline-sign.test.ts tests/models/offline-sign.test.ts tests/services/multisig.test.ts tests/services/hardware.test.ts tests/services/offline-sign.test.ts tests/services/tx/transaction-sender.test.ts tests/utils/multisig.test.ts tests/services/hardware/ledger.test.ts"
if [ "${2:-}" = "all" ]; then FILES=""; fi
ELECTRON_OVERRIDE_DIST_PATH=/nonexistent-electron ../../node_modules/.bin/jest --runInBand $FILES > ../../results/$1.log 2>&1
echo "exit=$?" >> ../../results/$1.log
