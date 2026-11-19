#!/bin/sh
# Rebuild src/ckb_cli_tx_helper.rs: ckb-cli v2.0.0's own init_witnesses and build_signature, taken from a ckb-cli
# checkout at tag v2.0.0 (80efc21c30e9fc7847407a217034681b6e46c763), with this experiment's header and the
# small change in ckb_cli_tx_helper.diff (init_witnesses as a free function). ckb-cli's code isn't copied here.
# Usage, from experiments/X1/rust:  sh make_tx_helper.sh <path to the ckb-cli checkout>
set -eu
sed -n '218,224p;507,566p' "$1/src/utils/tx_helper.rs" > src/ckb_cli_tx_helper.rs
patch -s src/ckb_cli_tx_helper.rs < ckb_cli_tx_helper.diff
echo "wrote src/ckb_cli_tx_helper.rs"
