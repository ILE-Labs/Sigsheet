#!/usr/bin/env python3
"""Fund every devnet case of X3, X4, X5 and XQ14 in one transaction from the miner key k0 (fresh devnet coins only).

Usage, from experiments/X5:  python3 -I -X utf8 scripts/fund_s4.py
Writes data/funding.json: the funding transaction's hash, and for each named configuration its lock, its
multisig config and its cells (out points). Run once; the cases spend these cells.

Configurations (members are fresh test keys s1-s5 and, where named L, the Ledger emulator's key at
m/44'/309'/0'/0/0 from Speculos's default test seed):
- L23G, L23V, L23B: 2-of-3 [L, s1, s2] under the genesis, v2 and 2024 deployments (XQ14);
- A23G, A23V, A23B: 2-of-3 [s1, s2, s3] under genesis, v2 and 2024 (X5, X4's high-s runs, S10, and the
  "device key isn't a member" run); A23VS: the same script under v2 with a since in the args (S11);
- B35V: 3-of-5 [s1..s5], R = 0; B35VR: the same members with R = 1 (s1 must sign) (X5);
- SK: a single-key cell of s4 (a mixed transaction in X5).
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import devnet  # noqa: E402

S = {n: devnet.KEYS[n]["blake160"] for n in ("s1", "s2", "s3", "s4", "s5")}
L = devnet.ledger_key_hash()
PLAN = [
    ("L23G", "genesis", 0, 2, [L, S["s1"], S["s2"]], None, 3),
    ("L23V", "v2", 0, 2, [L, S["s1"], S["s2"]], None, 1),
    ("L23B", "2024", 0, 2, [L, S["s1"], S["s2"]], None, 1),
    ("A23G", "genesis", 0, 2, [S["s1"], S["s2"], S["s3"]], None, 4),
    ("A23V", "v2", 0, 2, [S["s1"], S["s2"], S["s3"]], None, 5),
    ("A23B", "2024", 0, 2, [S["s1"], S["s2"], S["s3"]], None, 2),
    ("A23VS", "v2", 0, 2, [S["s1"], S["s2"], S["s3"]], 100, 1),
    ("B35V", "v2", 0, 3, [S["s1"], S["s2"], S["s3"], S["s4"], S["s5"]], None, 2),
    ("B35VR", "v2", 1, 3, [S["s1"], S["s2"], S["s3"], S["s4"], S["s5"]], None, 1),
]


def main():
    out_file = HERE / "data" / "funding.json"
    if out_file.exists():
        sys.exit("data/funding.json exists: already funded")
    outputs, names = [], []
    for name, dep, r, m, keys, since, n in PLAN:
        lock, cfg = devnet.multisig_lock(dep, r, m, keys, since)
        for _ in range(n):
            outputs.append({"capacity": hex(1000 * devnet.CKB), "lock": lock, "type": None})
            names.append((name, dep, lock, cfg, since))
    outputs.append({"capacity": hex(1000 * devnet.CKB), "lock": devnet.sighash_lock(S["s4"]), "type": None})
    names.append(("SK", "sighash", devnet.sighash_lock(S["s4"]), None, None))
    h, tx = devnet.fund(outputs)
    record = {"funding_tx": h, "rpc": devnet.RPC, "configs": {}}
    for i, (name, dep, lock, cfg, since) in enumerate(names):
        e = record["configs"].setdefault(name, {"deployment": dep, "lock": lock, "config": cfg,
                                                "since_in_args": since, "cells": []})
        e["cells"].append({"tx_hash": h, "index": hex(i)})
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(record, indent=1))
    (HERE / "data" / f"{h}.json").write_text(json.dumps({"rpc": devnet.RPC, "method": "get_transaction",
                                                         "result": devnet.rpc("get_transaction", [h])}, indent=1))
    print(h, len(outputs), "outputs")


if __name__ == "__main__":
    main()
