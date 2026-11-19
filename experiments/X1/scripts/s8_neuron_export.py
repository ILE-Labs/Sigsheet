#!/usr/bin/env python3
"""X1, case S8: what can be checked and computed from Neuron's offline JSON alone.

Usage, from experiments/X1:  python3 -I -X utf8 scripts/s8_neuron_export.py
Reads results/neuron-export/S8-neuron-export-after-first-signature.json (written by Neuron's own
OfflineSignController.exportTransactionAsJSON in the Neuron harness) and, with no node:
1. checks each `context` transaction hashes to its input's previousOutput.txHash, so the input
   cells it gives are genuine, and that they match the lock and capacity in Neuron's inputs;
2. converts Neuron's camelCase transaction (decimal strings, witness objects) to the RPC form;
3. recomputes the transaction hash and the multisig signing message (implementation M) and compares
   them with case S8;
4. recovers the partial signature's key and compares it with Neuron's `signatures` map.
Writes results/s8-neuron-export.json.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ckbcore as c  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent


def num_hex(v):
    """Neuron writes numbers as decimal strings ("6", "100000000000"); RPC uses 0x-hex."""
    v = str(v)
    return v if v.startswith("0x") else hex(int(v))


def script(s):
    return {"code_hash": s["codeHash"], "hash_type": s["hashType"], "args": s["args"]}


def to_rpc(t):
    def witness(w):
        if isinstance(w, str):
            return w
        return c.b2h(c.witness_args(*(c.h2b(w[k]) if w.get(k) else None for k in ("lock", "inputType", "outputType"))))
    return {
        "version": num_hex(t["version"]),
        "cell_deps": [{"out_point": {"tx_hash": d["outPoint"]["txHash"], "index": num_hex(d["outPoint"]["index"])},
                       "dep_type": {"depGroup": "dep_group", "code": "code"}[d["depType"]]} for d in t["cellDeps"]],
        "header_deps": t["headerDeps"],
        "inputs": [{"since": num_hex(i["since"]), "previous_output": {"tx_hash": i["previousOutput"]["txHash"],
                                                                    "index": num_hex(i["previousOutput"]["index"])}}
                   for i in t["inputs"]],
        "outputs": [{"capacity": num_hex(o["capacity"]), "lock": script(o["lock"]),
                     "type": script(o["type"]) if o.get("type") else None} for o in t["outputs"]],
        "outputs_data": t["outputsData"],
        "witnesses": [witness(w) for w in t["witnesses"]],
    }


def main():
    exp = json.loads((HERE / "results/neuron-export/S8-neuron-export-after-first-signature.json").read_text())
    case = json.loads((HERE / "cases/S8-neuron-export.json").read_text())
    msg_case = json.loads((HERE / "results/python.json").read_text())["messages"]["S8-neuron-export"]["V"]
    t = exp["transaction"]
    report = {"file_fields": list(exp.keys()), "status": exp["status"], "type": exp["type"], "checks": {}}

    # 1. context: the input transactions, hashed and matched to the inputs.
    ctx = {c.b2h(c.tx_hash(x)): x for x in exp["context"]}
    for n, i in enumerate(t["inputs"]):
        h, idx = i["previousOutput"]["txHash"], int(num_hex(i["previousOutput"]["index"]), 16)
        src = ctx.get(h)
        ok = src is not None
        cell = src["outputs"][idx] if ok else None
        report["checks"][f"input {n}: a context transaction hashes to its out point's tx hash"] = ok
        report["checks"][f"input {n}: Neuron's lock equals the context cell's lock"] = ok and script(i["lock"]) == cell["lock"]
        report["checks"][f"input {n}: Neuron's capacity equals the context cell's capacity"] = ok and num_hex(i["capacity"]) == cell["capacity"]

    # 2-3. the transaction hash and the message, from the file alone.
    rpc_tx = to_rpc(t)
    report["checks"]["transaction hash recomputed from the file equals case S8"] = c.b2h(c.tx_hash(rpc_tx)) == case["tx_hash"]
    report["checks"]["the hash Neuron wrote in transaction.hash equals it too"] = t.get("hash") == case["tx_hash"]
    w = [c.h2b(x) for x in rpc_tx["witnesses"]]
    lock, it, ot = c.parse_witness_args(w[0])
    n_keys, m = lock[3], lock[2]
    sl = 4 + 20 * n_keys
    report["partial_witness"] = {"lock_bytes": len(lock), "script_bytes": sl, "signatures_present": (len(lock) - sl) // 65,
                                 "threshold": m, "full_length_would_be": sl + 65 * m}
    zeroed = c.witness_args(lock[:sl] + bytes(65 * m), it, ot)
    msg = c.sighash_all_message(rpc_tx, [0], w, zeroed)
    report["message_from_file"] = c.b2h(msg)
    report["checks"]["message from the file equals the case S8 message"] = c.b2h(msg) == msg_case

    # 4. the partial signature and Neuron's signatures map.
    kh = c.b2h(c.blake160(c.recover(msg, lock[sl:sl + 65])))
    lock_hash = c.b2h(c.script_hash(rpc_tx and script(t["inputs"][0]["lock"])))
    report["checks"]["the partial signature recovers to a member key"] = kh in [c.b2h(lock[4 + 20 * i: 24 + 20 * i]) for i in range(n_keys)]
    report["checks"]["Neuron's signatures map lists that key under the input's lock hash"] = t.get("signatures", {}).get(lock_hash) == [kh]
    report["recovered_key_hash"] = kh
    (HERE / "results/s8-neuron-export.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
