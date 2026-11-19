#!/usr/bin/env python3
"""X1: verify every signature each tool produced, then build final transactions that mix tools and run them on devnet.

Usage, from experiments/X1:  python3 -I -X utf8 scripts/assemble.py
Inputs: cases/*.json, results/python.json, results/ccc.json, results/ckb-cli.json, results/neuron.json,
results/neuron-export/S8-neuron-export-after-first-signature.json.
1. Every signature from every tool is checked by recovering its public key with the message from
   scripts/ckbcore.py (implementation M) and comparing blake160(pubkey) with the signer's key hash.
2. For each devnet case, PLAN says which tool's signature to use for each signer. The final
   transaction is checked with test_tx_pool_accept and then sent with send_transaction; the script
   waits until it is committed. NEGATIVE entries must be rejected by test_tx_pool_accept.
3. S1 is finalized by ckb-cli itself: the other tools' signatures go into ckb-cli's tx file with
   `tx add-signature`, and `tx send` builds the witness and submits it.
Writes results/verify.json and results/assembly.json.
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ckbcore as c  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
KEYDIR = (HERE / "../../keys/x1").resolve()
KEYS = {k["name"]: k for k in json.loads((KEYDIR / "keys.json").read_text())}
RPC = "http://127.0.0.1:8114/"
ENV = dict(os.environ, CKB_CLI_HOME=str((HERE / "../../keys/ckb-cli-home").resolve()))

# case -> group -> [(signer key, tool)], tools: python, ccc, ckb-cli, neuron, neuron-export
PLAN = {
    "S2-2024-2of3": {"B": [("k1", "ccc"), ("k3", "python")]},
    "S3-v2-2of3-two-inputs": {"V": [("k2", "neuron"), ("k3", "ckb-cli")]},
    "S4-v2-first-R": {"VR": [("k4", "ccc"), ("k2", "ckb-cli")]},
    "S5-v2-since-in-args": {"VS": [("k1", "ckb-cli"), ("k3", "ccc")]},
    "S6-two-multisig-groups": {"G": [("k1", "neuron"), ("k2", "ckb-cli")],
                               "V35": [("k1", "ccc"), ("k3", "ckb-cli"), ("k5", "neuron")]},
    "S7-multisig-plus-single-key": {"V": [("k1", "ccc"), ("k2", "neuron")], "k7": [("k7", "ckb-cli")]},
    "S8-neuron-export": {"V": [("k1", "neuron-export"), ("k3", "ckb-cli")]},
    "S9-extra-witness": {"V": [("k2", "ckb-cli"), ("k3", "ccc")]},
}
NEGATIVE = {
    # first R: R=1 needs k4; k1 + k2 are two valid members but not the required one.
    "S4N-v2-first-R-missing-required": {"VR": [("k1", "python"), ("k2", "ckb-cli")]},
    # Neuron leaves out the witness beyond the inputs, so its signature fails on the full transaction.
    "S9-extra-witness": {"V": [("k2", "neuron"), ("k3", "ccc")]},
}


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def wait_committed(h, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = rpc("get_transaction", [h]).get("result")
        if r and r["tx_status"]["status"] == "committed":
            return int(r["tx_status"]["block_number"], 16)
        time.sleep(1)
    return None


def load_tools():
    py = json.loads((HERE / "results/python.json").read_text())
    ccc = json.loads((HERE / "results/ccc.json").read_text())
    cli = json.loads((HERE / "results/ckb-cli.json").read_text())
    neu = json.loads((HERE / "results/neuron.json").read_text())
    sigs = {}  # (case, group, key, tool) -> signature hex

    def put(cid, g, k, tool, s):
        if s:
            sigs[(cid, g, k, tool)] = s
    cases = {json.loads(f.read_text())["id"]: json.loads(f.read_text()) for f in (HERE / "cases").glob("*.json")}
    for cid, gs in py["signatures"].items():
        for g, ks in gs.items():
            for k, s in ks.items():
                put(cid, g, k, "python", s)
    for cid, gs in ccc["signatures"].items():
        for g, ks in gs.items():
            for k, s in ks.items():
                put(cid, g, k, "ccc", s)
    for cid, ks in cli["cases"].items():
        for k, e in ks.items():
            for item in e.get("output") or []:
                la = item["lock-arg"]
                for g in cases[cid]["groups"]:
                    if g["lock"]["args"] == la:
                        put(cid, g["name"], k, "ckb-cli", item["signature"])
    for cid, cc in neu["cases"].items():
        for g, gr in cc["groups"].items():
            for k, s in (gr.get("signatures") or {}).items():
                put(cid, g, k, "neuron", s)
            fw = gr.get("final_witness")
            if isinstance(fw, str) and fw.startswith("0x"):
                # Neuron appends each signature after the multisig script, in signing order
                # (transaction-sender.ts lines 429-433), so slot i belongs to the i-th signer.
                lock, _, _ = c.parse_witness_args(c.h2b(fw))
                sl = 4 + 20 * lock[3]
                signers = next(x["signers"] for x in cases[cid]["groups"] if x["name"] == g)
                for i, k in enumerate(signers):
                    put(cid, g, k, "neuron", c.b2h(lock[sl + 65 * i: sl + 65 * (i + 1)]))
    exp = json.loads((HERE / "results/neuron-export/S8-neuron-export-after-first-signature.json").read_text())
    lock = c.h2b(exp["transaction"]["witnesses"][0]["lock"])
    sl = 4 + 20 * lock[3]
    put("S8-neuron-export", "V", "k1", "neuron-export", c.b2h(lock[sl:sl + 65]))
    return cases, py["messages"], sigs


def verify_all(cases, messages, sigs):
    table = {}
    for (cid, g, k, tool), s in sorted(sigs.items()):
        msg = c.h2b(messages[cid][g])
        try:
            kh = c.b2h(c.blake160(c.recover(msg, c.h2b(s))))
            ok = kh == KEYS[k]["blake160"]
        except ValueError as e:
            kh, ok = str(e), False
        table.setdefault(cid, {}).setdefault(g, {}).setdefault(k, {})[tool] = {"signature": s, "valid_for_M_message": ok}
    return table


def final_tx(case, plan, sigs):
    tx = json.loads(json.dumps(case["tx"]))
    w = [c.h2b(x) for x in tx["witnesses"]]
    for g in case["groups"]:
        chosen = []
        for k, tool in plan[g["name"]]:
            if (case["id"], g["name"], k, tool) not in sigs and tool == "python":
                # Implementation M signs any key on demand (negative controls need non-designated keys).
                zeroed = c.zeroed_first_witness(w[g["input_indices"][0]]) if g["kind"] == "multisig" else None
                msg = (c.multisig_message(tx, g["input_indices"], w) if g["kind"] == "multisig"
                       else c.sighash_all_message(tx, g["input_indices"], w, c.sighash_zeroed_first_witness(w[g["input_indices"][0]])))
                sigs[(case["id"], g["name"], k, tool)] = c.b2h(c.sign(msg, c.h2b(KEYS[k]["secret"])))
            chosen.append(sigs[(case["id"], g["name"], k, tool)])
        first = g["input_indices"][0]
        _, it, ot = c.parse_witness_args(w[first])
        if g["kind"] == "multisig":
            lock = c.h2b(g["script"]) + b"".join(c.h2b(s) for s in chosen)
        else:
            lock = c.h2b(chosen[0])
        w[first] = c.witness_args(lock, it, ot)
    tx["witnesses"] = [c.b2h(x) for x in w]
    return tx


def neuron_own_s9(case):
    """Neuron's own final transaction for S9, as its signMultisig returned it: the witness beyond the inputs dropped."""
    neu = json.loads((HERE / "results/neuron.json").read_text())["cases"]["S9-extra-witness"]["groups"]["V"]
    tx = json.loads(json.dumps(case["tx"]))
    tx["witnesses"] = [neu["final_witness"]]
    return tx


def ckbcli_finalize_s1(case, sigs):
    """Put Neuron's k1 and CCC's k2 signatures into ckb-cli's tx file with add-signature; ckb-cli sends."""
    path = HERE / "results" / "ckb-cli" / "S1-genesis-2of3.json"
    g = case["groups"][0]
    log = []
    for k, tool in [("k1", "neuron"), ("k2", "ccc")]:
        cmd = ["ckb-cli", "--url", RPC, "tx", "add-signature", "--tx-file", str(path),
               "--lock-arg", g["lock"]["args"], "--signature", sigs[(case["id"], "G", k, tool)]]
        p = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
        log.append({"command": " ".join(cmd), "exit": p.returncode, "out": (p.stdout + p.stderr)[-400:]})
    cmd = ["ckb-cli", "--url", RPC, "tx", "send", "--tx-file", str(path), "--output-format", "json"]
    p = subprocess.run(cmd, capture_output=True, text=True, env=ENV)
    log.append({"command": " ".join(cmd), "exit": p.returncode, "out": (p.stdout + p.stderr)[-600:]})
    h = p.stdout.strip().strip('"').splitlines()[-1].strip().strip('"') if p.returncode == 0 else None
    return h, log


def main():
    cases, messages, sigs = load_tools()
    table = verify_all(cases, messages, sigs)
    (HERE / "results/verify.json").write_text(json.dumps(table, indent=1))
    bad = [(cid, g, k, t) for cid, gs in table.items() for g, ks in gs.items() for k, ts in ks.items()
           for t, v in ts.items() if not v["valid_for_M_message"]]
    print(f"{sum(len(ts) for gs in table.values() for ks in gs.values() for ts in ks.values())} signatures checked; "
          f"not valid for the lock's message: {bad}")

    prev = HERE / "results/assembly.json"
    out = json.loads(prev.read_text()) if prev.exists() else {"rpc": RPC, "runs": []}
    done = {r["case"] for r in out["runs"] if r.get("committed_block")}

    def committed(cid):
        r = rpc("get_transaction", [cases[cid]["tx_hash"]]).get("result")
        return r and r["tx_status"]["status"] == "committed"
    # Negative controls first: they must be rejected and change nothing.
    for cid, plan in NEGATIVE.items():
        if committed(cid) or any(r["case"] == cid and r["kind"] == "negative" for r in out["runs"]):
            continue
        tx = final_tx(cases[cid], plan, sigs)
        r = rpc("test_tx_pool_accept", [tx, "passthrough"])
        out["runs"].append({"case": cid, "kind": "negative", "plan": plan,
                            "accepted": "result" in r, "error": r.get("error", {}).get("message", "")[:300]})
        print("NEGATIVE", cid, "accepted" if "result" in r else "rejected: " + r["error"]["message"][:160])
    # Neuron's own S9 transaction (extra witness dropped): checked, not sent.
    tx = neuron_own_s9(cases["S9-extra-witness"])
    r = rpc("test_tx_pool_accept", [tx, "passthrough"]) if not committed("S9-extra-witness") else {"error": {"message": "skipped: S9 already committed"}}
    out["runs"].append({"case": "S9-extra-witness", "kind": "neuron's own transaction (extra witness dropped), dry run",
                        "accepted": "result" in r, "error": r.get("error", {}).get("message", "")[:300]})
    print("S9 neuron-own", "accepted (dry run)" if "result" in r else "rejected: " + r["error"]["message"][:160])
    # S1 through ckb-cli's own finalize and send.
    h, log = ckbcli_finalize_s1(cases["S1-genesis-2of3"], sigs) if not committed("S1-genesis-2of3") else (cases["S1-genesis-2of3"]["tx_hash"], [{"note": "already committed in an earlier run"}])
    blk = wait_committed(h) if h else None
    out["runs"].append({"case": "S1-genesis-2of3", "kind": "finalized and sent by ckb-cli tx send",
                        "signatures": {"k1": "neuron", "k2": "ccc"}, "tx_hash": h, "committed_block": blk, "log": log})
    print("S1 via ckb-cli", h, "block", blk)
    # The rest: dry run, then send and wait.
    for cid, plan in PLAN.items():
        if committed(cid):
            blk = wait_committed(cases[cid]["tx_hash"])
            if cid not in done:
                out["runs"].append({"case": cid, "kind": "mixed tools, sent", "plan": plan,
                                    "tx_hash": cases[cid]["tx_hash"], "committed_block": blk,
                                    "note": "committed in an earlier run of this script"})
            print(cid, "already committed, block", blk)
            continue
        tx = final_tx(cases[cid], plan, sigs)
        dry = rpc("test_tx_pool_accept", [tx, "passthrough"])
        sent = rpc("send_transaction", [tx, "passthrough"]) if "result" in dry else {}
        h = sent.get("result")
        blk = wait_committed(h) if h else None
        out["runs"].append({"case": cid, "kind": "mixed tools, sent", "plan": plan,
                            "dry_run": dry.get("result") or dry.get("error"), "tx_hash": h, "committed_block": blk})
        print(cid, h, "block", blk, "" if h else json.dumps(dry.get("error"))[:200])
    (HERE / "results/assembly.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
