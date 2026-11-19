#!/usr/bin/env python3
"""Record the devnet genesis: every system cell's data hash and type script hash, and every dep group.

Usage, from experiments/X1:  python3 -I -X utf8 scripts/devnet_info.py [rpc url]   (default http://127.0.0.1:8114/)
Writes data/devnet/genesis-info.json and prints how each multisig cell compares with mainnet
(data/mainnet/summary.json, made by fetch_mainnet.py).
"""
import json
import pathlib
import sys
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ckbcore as c  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
RPC = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8114/"


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(out["error"])
    return out["result"]


def main():
    g = rpc("get_block_by_number", ["0x0"])
    cells = []
    for tx in g["transactions"]:
        assert c.b2h(c.tx_hash(tx)) == tx["hash"]
        for i, (o, d) in enumerate(zip(tx["outputs"], tx["outputs_data"])):
            data = c.h2b(d)
            cells.append({"out_point": f'{tx["hash"]}:{i}', "data_bytes": len(data),
                          "data_hash": c.b2h(c.ckbhash(data)),
                          "type_script_hash": c.b2h(c.script_hash(o["type"])) if o.get("type") else None,
                          "dep_group_lists": [f"{c.b2h(data[4 + 36 * k: 36 + 36 * k])}:"
                                              f"{int.from_bytes(data[36 + 36 * k: 40 + 36 * k], 'little')}"
                                              for k in range(int.from_bytes(data[:4], 'little'))]
                          if tx is g["transactions"][1] else None})
    mainnet = json.loads((HERE / "data" / "mainnet" / "summary.json").read_text())["deployments"]
    by_data = {x["data_hash"]: x for x in cells}
    compare = {}
    for name, dep in mainnet.items():
        m = dep["multisig_code_cell"]
        d = by_data.get(m["data_hash"])
        groups = [x for x in cells if x["dep_group_lists"] and d and d["out_point"] in x["dep_group_lists"]]
        compare[name] = {"mainnet_data_hash": m["data_hash"], "mainnet_type_hash": m["type_script_hash"],
                         "devnet_cell": d["out_point"] if d else None,
                         "devnet_type_hash": d["type_script_hash"] if d else None,
                         "devnet_dep_group": groups[0]["out_point"] if groups else None,
                         "same_binary": bool(d)}
    out = {"rpc": RPC, "genesis_hash": g["header"]["hash"], "cells": cells, "multisig": compare}
    (HERE / "data" / "devnet").mkdir(parents=True, exist_ok=True)
    (HERE / "data" / "devnet" / "genesis-info.json").write_text(json.dumps(out, indent=1))
    print("genesis", g["header"]["hash"])
    print(json.dumps(compare, indent=1))


if __name__ == "__main__":
    main()
