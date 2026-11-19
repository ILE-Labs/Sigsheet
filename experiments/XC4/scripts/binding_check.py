#!/usr/bin/env python3
"""XC4 step 4: what binding an IDL would do to the deployed multisig code cells.

Usage, from experiments/XC4 (after `ckb-idl bind` wrote results/bind-sim/v2/):
    python3 -I -X utf8 scripts/binding_check.py > results/binding-check.json

For each deployment: the code cell's data hash (ckbhash = blake2b-256, personalisation
"ckb-default-hash"), its last 8 bytes against Binding Trailer 1's magic, and the lock of the code cell
as recorded from mainnet in X1. For v2 (hash_type data1, where the script's code hash IS the data hash),
also the data hash of the bound executable that ckb-idl's own `bind` produced.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
X1 = HERE.parent / "X1"
sys.path.insert(0, str(X1 / "scripts"))
import ckbcore  # noqa: E402

MAGIC = bytes.fromhex("434b4249444c0000")
summary = json.loads((X1 / "data/mainnet/summary.json").read_text())
genesis = json.loads((X1 / "data/mainnet/genesis-block.json").read_text())["result"]


def code_cell_lock(dep):
    tx_hash, index = dep["multisig_code_cell"]["out_point"].split(":")
    if tx_hash == genesis["transactions"][0]["hash"]:
        return genesis["transactions"][0]["outputs"][int(index)]["lock"]
    tx = json.loads((X1 / f"data/mainnet/{tx_hash}.json").read_text())["result"]["transaction"]
    return tx["outputs"][int(index)]["lock"]


out = {}
for name, binfile in (("genesis", "multisig-genesis.bin"), ("2024", "multisig-2024.bin"), ("v2", "multisig-v2.bin")):
    dep = summary["deployments"][name]
    data = (X1 / "data/mainnet" / binfile).read_bytes()
    out[name] = {
        "hash_type": dep["hash_type"],
        "code_hash": dep["expected_code_hash"],
        "code_cell": dep["multisig_code_cell"]["out_point"],
        "data_bytes": len(data),
        "data_hash": "0x" + ckbcore.ckbhash(data).hex(),
        "recorded_data_hash": dep["multisig_code_cell"]["data_hash"],
        "ends_with_trailer_magic": data[-8:] == MAGIC,
        "last_8_bytes": data[-8:].hex(),
        "code_cell_lock": code_cell_lock(dep),
    }
bound = HERE / "results/bind-sim/v2/multisig-v2.bin"
if bound.exists():
    b = bound.read_bytes()
    out["v2"]["bound_by_ckb_idl_bind"] = {"bytes": len(b), "data_hash": "0x" + ckbcore.ckbhash(b).hex(),
                                          "equals_v2_code_hash": "0x" + ckbcore.ckbhash(b).hex() == out["v2"]["code_hash"],
                                          "trailer_hex": b[-46:].hex()}
json.dump(out, sys.stdout, indent=1)
print()
