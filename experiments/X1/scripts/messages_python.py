#!/usr/bin/env python3
"""X1, implementation M: the signing message of every lock group in every case, from scripts/ckbcore.py.

Usage, from experiments/X1:  python3 -I -X utf8 scripts/messages_python.py
Writes results/python.json: {case id: {group name: message}}.
Also signs each synthetic case's groups with their designated test keys and writes the signatures,
so other tools' merged transactions can mix in signatures from this implementation.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ckbcore as c  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
KEYS = {k["name"]: k for k in json.loads((HERE / "../../keys/x1/keys.json").read_text())}


def group_message(case, g):
    tx = case["tx"]
    w = [c.h2b(x) for x in tx["witnesses"]]
    idx = g["input_indices"]
    if g["kind"] == "multisig":
        return c.multisig_message(tx, idx, w)
    return c.sighash_all_message(tx, idx, w, c.sighash_zeroed_first_witness(w[idx[0]]))


def main():
    out, sigs = {}, {}
    for f in sorted((HERE / "cases").glob("*.json")):
        case = json.loads(f.read_text())
        assert c.b2h(c.tx_hash(case["tx"])) == case["tx_hash"]
        out[case["id"]] = {}
        for g in case["groups"]:
            msg = group_message(case, g)
            out[case["id"]][g["name"]] = c.b2h(msg)
            for k in g.get("signers", []):
                sigs.setdefault(case["id"], {}).setdefault(g["name"], {})[k] = c.b2h(
                    c.sign(msg, c.h2b(KEYS[k]["secret"])))
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "python.json").write_text(json.dumps({"messages": out, "signatures": sigs}, indent=1))
    for cid, gs in out.items():
        for g, m in gs.items():
            print(f"{cid:30} {g:24} {m}")


if __name__ == "__main__":
    main()
