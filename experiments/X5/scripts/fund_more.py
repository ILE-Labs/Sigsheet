#!/usr/bin/env python3
"""Fund more cells for configurations already in data/funding.json, from the miner key k0 (devnet coins only).

Usage, from experiments/X5:  python3 -I -X utf8 scripts/fund_more.py NAME=COUNT [NAME=COUNT ...]
Appends the new cells to each configuration's "cells" list in data/funding.json and records the funding
transaction under "more_funding". The cells already listed keep their numbers.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import devnet  # noqa: E402


def main():
    f = HERE / "data" / "funding.json"
    rec = json.loads(f.read_text())
    plan = [(a.split("=")[0], int(a.split("=")[1])) for a in sys.argv[1:]]
    outputs, names = [], []
    for name, n in plan:
        e = rec["configs"][name]
        for _ in range(n):
            outputs.append({"capacity": hex(1000 * devnet.CKB), "lock": e["lock"], "type": None})
            names.append(name)
    h, _ = devnet.fund(outputs)
    for i, name in enumerate(names):
        rec["configs"][name]["cells"].append({"tx_hash": h, "index": hex(i)})
    rec.setdefault("more_funding", []).append({"tx": h, "plan": dict(plan)})
    f.write_text(json.dumps(rec, indent=1))
    (HERE / "data" / f"{h}.json").write_text(json.dumps({"rpc": devnet.RPC, "method": "get_transaction",
                                                         "result": devnet.rpc("get_transaction", [h])}, indent=1))
    print(h, len(outputs))


if __name__ == "__main__":
    main()
