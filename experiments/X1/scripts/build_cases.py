#!/usr/bin/env python3
"""Build the X1 cases: fund the multisig cells on the local devnet, then write one case file per case.

Usage, from experiments/X1:  python3 -I -X utf8 scripts/build_cases.py
Needs: the devnet running (http://127.0.0.1:8114/), keys in ../../keys/x1/keys.json (scripts/keygen.py),
data/devnet/genesis-info.json (scripts/devnet_info.py), and the mainnet data (scripts/fetch_mainnet.py).
Writes cases/<id>.json. Each case holds the unsigned transaction (RPC form, with placeholder witnesses),
the resolved input cells, and one entry per lock group: its lock, input indices, kind, deployment,
multisig config and the test keys that will sign it.
"""
import json
import pathlib
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ckbcore as c  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
RPC = "http://127.0.0.1:8114/"
_KEYFILE = HERE / "../../keys/x1/keys.json"
KEYS = {k["name"]: k for k in json.loads(_KEYFILE.read_text())} if _KEYFILE.exists() else {}  # none needed for --real-only
GEN = json.loads((HERE / "data/devnet/genesis-info.json").read_text())
FEE = 100_000  # shannons per transaction
CKB = 100_000_000


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(f"{method}: {out['error']}")
    return out["result"]


def wait_committed(h, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = rpc("get_transaction", [h])
        if r and r["tx_status"]["status"] == "committed":
            return r["tx_status"]["block_hash"]
        time.sleep(1)
    raise SystemExit(f"{h} not committed after {timeout} s")


# ------------------------------------------------------------------ scripts and deps

def dep(name):
    """Genesis dep groups on this devnet: tx 1 outputs 0 (sighash), 1 (genesis multisig), 2 (2024), 3 (v2).
    devnet_info.py records the same out points under "multisig" -> "devnet_dep_group"."""
    return {"genesis": 1, "2024": 2, "v2": 3, "sighash": 0}[name]


DEP_TX = [x for x in GEN["cells"] if x["dep_group_lists"]][0]["out_point"].split(":")[0]
CODE = {
    "genesis": ("0x5c5069eb0857efc65e1bca0c07df34c31663b3622fd3876c876320fc9634e2a8", "type"),
    "2024": (GEN["multisig"]["2024"]["devnet_type_hash"], "type"),
    "v2": ("0x36c971b8d41fbd94aabca77dc75e826729ac98447b46f91e00796155dddb0d29", "data1"),
}


def cell_dep(name):
    return {"out_point": {"tx_hash": DEP_TX, "index": hex(dep(name))}, "dep_type": "dep_group"}


def sighash_lock(key):
    return {"code_hash": c.SIGHASH_CODE_HASH, "hash_type": "type", "args": KEYS[key]["blake160"]}


def multisig(deployment, r, m, keys, since=None):
    hashes = [c.h2b(KEYS[k]["blake160"]) for k in keys]
    script = c.multisig_script(r, m, hashes)
    args = c.blake160(script) + (c.u64(since) if since is not None else b"")
    code_hash, hash_type = CODE[deployment]
    return {"deployment": deployment, "lock": {"code_hash": code_hash, "hash_type": hash_type, "args": c.b2h(args)},
            "multisig": {"require_first_n": r, "threshold": m, "key_hashes": [KEYS[k]["blake160"] for k in keys]},
            "members": keys, "script": c.b2h(script), "since_in_args": since}


# The synthetic cases' multisig configs need the test keys; --real-only (the mainnet cases) needs none.
CONFIGS = {} if not KEYS else {
    "G": multisig("genesis", 0, 2, ["k1", "k2", "k3"]),
    "B": multisig("2024", 0, 2, ["k1", "k2", "k3"]),
    "V": multisig("v2", 0, 2, ["k1", "k2", "k3"]),
    "VR": multisig("v2", 1, 2, ["k4", "k1", "k2"]),          # k4 (the first key) must sign
    "VS": multisig("v2", 0, 2, ["k1", "k2", "k3"], since=20),  # absolute block number 20
    "V35": multisig("v2", 0, 3, ["k1", "k2", "k3", "k4", "k5"]),
}


def output(lock, capacity):
    return {"capacity": hex(capacity), "lock": lock, "type": None}


def placeholder_multisig_witness(cfg):
    lock = c.h2b(cfg["script"]) + bytes(65 * cfg["multisig"]["threshold"])
    return c.b2h(c.witness_args(lock))


def placeholder_sighash_witness():
    return c.b2h(c.witness_args(bytes(65)))


# ------------------------------------------------------------------ funding

def genesis_cell_of(key):
    g = rpc("get_block_by_number", ["0x0"])
    tx0 = g["transactions"][0]
    for i, o in enumerate(tx0["outputs"]):
        if o["lock"]["args"] == KEYS[key]["blake160"] and o["lock"]["code_hash"] == c.SIGHASH_CODE_HASH:
            return {"tx_hash": tx0["hash"], "index": hex(i)}, o
    raise SystemExit(f"no genesis cell for {key}")


def sign_sighash(tx, group, key, witnesses):
    zeroed = c.sighash_zeroed_first_witness(witnesses[group[0]])
    msg = c.sighash_all_message(tx, group, witnesses, zeroed)
    sig = c.sign(msg, c.h2b(KEYS[key]["secret"]))
    _, it, ot = c.parse_witness_args(witnesses[group[0]])
    witnesses[group[0]] = c.witness_args(sig, it, ot)


def fund():
    """One transaction from k0's genesis cell: every multisig cell the cases spend, plus one k7 cell."""
    plan = [("G", 2), ("B", 1), ("V", 5), ("VR", 1), ("VS", 1), ("V35", 1)]
    outs, names = [], []
    for name, n in plan:
        for _ in range(n):
            outs.append(output(CONFIGS[name]["lock"], 1000 * CKB))
            names.append(name)
    outs.append(output(sighash_lock("k7"), 1000 * CKB))
    names.append("k7")
    op, cell = genesis_cell_of("k0")
    change = int(cell["capacity"], 16) - sum(int(o["capacity"], 16) for o in outs) - FEE
    outs.append(output(sighash_lock("k0"), change))
    names.append("k0-change")
    tx = {"version": "0x0", "cell_deps": [cell_dep("sighash")], "header_deps": [],
          "inputs": [{"since": "0x0", "previous_output": op}], "outputs": outs,
          "outputs_data": ["0x"] * len(outs), "witnesses": [placeholder_sighash_witness()]}
    w = [c.h2b(x) for x in tx["witnesses"]]
    sign_sighash(tx, [0], "k0", w)
    tx["witnesses"] = [c.b2h(x) for x in w]
    h = rpc("send_transaction", [tx, "passthrough"])
    assert h == c.b2h(c.tx_hash(tx))
    wait_committed(h)
    cells = {}
    for i, (name, o) in enumerate(zip(names, outs)):
        cells.setdefault(name, []).append({"out_point": {"tx_hash": h, "index": hex(i)}, "output": o, "data": "0x"})
    return h, cells


# ------------------------------------------------------------------ cases

def case(cid, description, inputs, outputs, groups, extra_witnesses=(), since=None):
    """inputs: list of (cell, group name); groups: {name: {"config": cfg or None, "key": sighash key, "signers": [...]}}."""
    tx = {"version": "0x0", "cell_deps": [], "header_deps": [], "inputs": [], "outputs": outputs,
          "outputs_data": ["0x"] * len(outputs), "witnesses": []}
    deps = []
    gs = {}
    for idx, (cell, gname) in enumerate(inputs):
        g = groups[gname]
        tx["inputs"].append({"since": hex(since if (since is not None and g.get("config") and g["config"]["since_in_args"] is not None) else 0),
                             "previous_output": cell["out_point"]})
        gs.setdefault(gname, []).append(idx)
        d = g["config"]["deployment"] if g.get("config") else "sighash"
        if d not in deps:
            deps.append(d)
    tx["cell_deps"] = [cell_dep(d) for d in deps]
    witnesses = ["0x"] * len(inputs)
    out_groups = []
    for gname, idxs in gs.items():
        g = groups[gname]
        if g.get("config"):
            witnesses[idxs[0]] = placeholder_multisig_witness(g["config"])
            cfg = g["config"]
            out_groups.append({"name": gname, "kind": "multisig", "deployment": cfg["deployment"], "lock": cfg["lock"],
                               "input_indices": idxs, "multisig": cfg["multisig"], "members": cfg["members"],
                               "script": cfg["script"], "since_in_args": cfg["since_in_args"],
                               "signers": g["signers"]})
        else:
            witnesses[idxs[0]] = placeholder_sighash_witness()
            out_groups.append({"name": gname, "kind": "sighash", "deployment": "sighash", "lock": sighash_lock(g["key"]),
                               "input_indices": idxs, "signers": [g["key"]]})
    tx["witnesses"] = witnesses + list(extra_witnesses)
    total_in = sum(int(cell["output"]["capacity"], 16) for cell, _ in inputs)
    total_out = sum(int(o["capacity"], 16) for o in outputs)
    assert total_in - total_out == FEE, (cid, total_in, total_out)
    body = {"id": cid, "network": "devnet", "description": description, "tx": tx,
            "tx_hash": c.b2h(c.tx_hash(tx)),
            "input_cells": [{"out_point": cell["out_point"], "output": cell["output"], "data": cell["data"]}
                            for cell, _ in inputs],
            "groups": out_groups}
    (HERE / "cases" / f"{cid}.json").write_text(json.dumps(body, indent=1))
    print(cid, body["tx_hash"])


def pay(lock_cells, cfg_lock, to_key="k6", amount=100 * CKB):
    total = sum(int(x["output"]["capacity"], 16) for x in lock_cells)
    return [output(sighash_lock(to_key), amount), output(cfg_lock, total - amount - FEE)]


def build_synthetic(cells):
    G, B, V, VR, VS, V35 = (CONFIGS[k] for k in ("G", "B", "V", "VR", "VS", "V35"))
    case("S1-genesis-2of3", "Genesis deployment (type), 2-of-3, R=0; one multisig input",
         [(cells["G"][0], "G")], pay([cells["G"][0]], G["lock"]),
         {"G": {"config": G, "signers": ["k1", "k2"]}})
    case("S2-2024-2of3", "2024 deployment (type id, binary from mainnet), 2-of-3, R=0",
         [(cells["B"][0], "B")], pay([cells["B"][0]], B["lock"]),
         {"B": {"config": B, "signers": ["k1", "k3"]}})
    case("S3-v2-2of3-two-inputs", "v2 deployment (data1), 2-of-3, two inputs in one lock group",
         [(cells["V"][0], "V"), (cells["V"][1], "V")], pay(cells["V"][0:2], V["lock"]),
         {"V": {"config": V, "signers": ["k2", "k3"]}})
    case("S4-v2-first-R", "v2, R=1, M=2, N=3: the first key (k4) must sign",
         [(cells["VR"][0], "VR")], pay([cells["VR"][0]], VR["lock"]),
         {"VR": {"config": VR, "signers": ["k4", "k2"]}})
    case("S5-v2-since-in-args", "v2, 2-of-3, lock args carry since = absolute block 20; input since 20",
         [(cells["VS"][0], "VS")], pay([cells["VS"][0]], VS["lock"]),
         {"VS": {"config": VS, "signers": ["k1", "k3"]}}, since=20)
    gcell, mcell = cells["G"][1], cells["V35"][0]
    case("S6-two-multisig-groups", "Two multisig lock groups: genesis 2-of-3 and v2 3-of-5",
         [(gcell, "G"), (mcell, "V35")],
         [output(sighash_lock("k6"), 100 * CKB), output(G["lock"], int(gcell["output"]["capacity"], 16) - 100 * CKB),
          output(V35["lock"], int(mcell["output"]["capacity"], 16) - FEE)],
         {"G": {"config": G, "signers": ["k1", "k2"]}, "V35": {"config": V35, "signers": ["k1", "k3", "k5"]}})
    vcell, kcell = cells["V"][2], cells["k7"][0]
    case("S7-multisig-plus-single-key", "A v2 2-of-3 input next to an ordinary single-key (sighash) input",
         [(vcell, "V"), (kcell, "k7")],
         [output(sighash_lock("k6"), 100 * CKB), output(V["lock"], int(vcell["output"]["capacity"], 16) - 100 * CKB),
          output(sighash_lock("k7"), int(kcell["output"]["capacity"], 16) - FEE)],
         {"V": {"config": V, "signers": ["k1", "k2"]}, "k7": {"key": "k7"}})
    case("S8-neuron-export", "v2 2-of-3, signed first in Neuron and exported as Neuron's offline JSON, then completed by others",
         [(cells["V"][3], "V")], pay([cells["V"][3]], V["lock"]),
         {"V": {"config": V, "signers": ["k1", "k3"]}})
    case("S9-extra-witness", "v2 2-of-3 with one witness beyond the inputs (index 1, 4 bytes), which the lock hashes",
         [(cells["V"][4], "V")], pay([cells["V"][4]], V["lock"]),
         {"V": {"config": V, "signers": ["k2", "k3"]}}, extra_witnesses=["0xdeadbeef"])


def build_real():
    """R1: fiber-scripts PR #34 cell_tx; R2: a 2-of-3 genesis multisig payment on mainnet. Groups from the input cells."""
    d = json.loads((HERE / "data/fiber-scripts-34/mainnet.json").read_text())
    tx = d["cell_tx"]
    used = d["used_input_txs"]
    inputs = []
    for i in tx["inputs"]:
        p = i["previous_output"]
        src = used[p["tx_hash"]]
        k = int(p["index"], 16)
        inputs.append({"out_point": p, "output": src["outputs"][k], "data": src["outputs_data"][k]})
    lock0, _, _ = c.parse_witness_args(c.h2b(tx["witnesses"][0]))
    info = c.parse_multisig_script(lock0)
    sl = 4 + 20 * len(info["keys"])
    groups = [{"name": "fiber-deploy-multisig", "kind": "multisig", "deployment": "v2", "lock": inputs[0]["output"]["lock"],
               "input_indices": [0], "script": c.b2h(lock0[:sl]), "since_in_args": None,
               "multisig": {"require_first_n": info["require_first_n"], "threshold": info["threshold"],
                            "key_hashes": [c.b2h(k) for k in info["keys"]]}, "signers": []},
              {"name": "fee-payer-single-key", "kind": "sighash", "deployment": "sighash",
               "lock": inputs[1]["output"]["lock"], "input_indices": [1], "signers": []}]
    body = {"id": "R1-fiber-scripts-pr34", "network": "mainnet",
            "description": "fiber-scripts PR #34 cell_tx from deployment/mainnet/mainnet.json at 026027f (3-of-5 v2 multisig plus one single-key input)",
            "tx": tx, "tx_hash": c.b2h(c.tx_hash(tx)), "input_cells": inputs, "groups": groups}
    (HERE / "cases" / "R1-fiber-scripts-pr34.json").write_text(json.dumps(body, indent=1))
    print(body["id"], body["tx_hash"])

    p = json.loads((HERE / "data/mainnet/0x63a7f3a52fc91c52939186ca9c1064238ccdfe498d3398f25707537f591bbaa4.json").read_text())
    tx = p["result"]["transaction"]
    tx = {k: v for k, v in tx.items() if k != "hash"}
    inputs = []
    for i in tx["inputs"]:
        q = i["previous_output"]
        src = json.loads((HERE / f"data/mainnet/{q['tx_hash']}.json").read_text())["result"]["transaction"]
        k = int(q["index"], 16)
        inputs.append({"out_point": q, "output": src["outputs"][k], "data": src["outputs_data"][k]})
    lock0, _, _ = c.parse_witness_args(c.h2b(tx["witnesses"][0]))
    info = c.parse_multisig_script(lock0)
    sl = 4 + 20 * len(info["keys"])
    groups = [{"name": "dao-payout-multisig", "kind": "multisig", "deployment": "genesis", "lock": inputs[0]["output"]["lock"],
               "input_indices": [0], "script": c.b2h(lock0[:sl]), "since_in_args": None,
               "multisig": {"require_first_n": info["require_first_n"], "threshold": info["threshold"],
                            "key_hashes": [c.b2h(k) for k in info["keys"]]}, "signers": []}]
    body = {"id": "R2-dao-payout", "network": "mainnet",
            "description": "a 2-of-3 genesis multisig payment on mainnet, tx 0x63a7f3a5...baa4 at block 20,354,743, as committed",
            "tx": tx, "tx_hash": c.b2h(c.tx_hash(tx)), "input_cells": inputs, "groups": groups}
    (HERE / "cases" / "R2-dao-payout.json").write_text(json.dumps(body, indent=1))
    print(body["id"], body["tx_hash"])


def extra():
    """S4N: a fresh R=1 cell for the negative control (two valid members, but not the required one).
    Funded from k0's change output of the first funding transaction."""
    f = json.loads((HERE / "data/devnet/funding.json").read_text())
    ch = f["cells"]["k0-change"][0]
    VR = CONFIGS["VR"]
    outs = [output(VR["lock"], 1000 * CKB)]
    change = int(ch["output"]["capacity"], 16) - 1000 * CKB - FEE
    outs.append(output(sighash_lock("k0"), change))
    tx = {"version": "0x0", "cell_deps": [cell_dep("sighash")], "header_deps": [],
          "inputs": [{"since": "0x0", "previous_output": ch["out_point"]}], "outputs": outs,
          "outputs_data": ["0x"] * len(outs), "witnesses": [placeholder_sighash_witness()]}
    w = [c.h2b(x) for x in tx["witnesses"]]
    sign_sighash(tx, [0], "k0", w)
    tx["witnesses"] = [c.b2h(x) for x in w]
    h = rpc("send_transaction", [tx, "passthrough"])
    wait_committed(h)
    cell = {"out_point": {"tx_hash": h, "index": "0x0"}, "output": outs[0], "data": "0x"}
    (HERE / "data/devnet/funding-extra.json").write_text(json.dumps({"funding_tx": h, "cells": {"VR": [cell]}}, indent=1))
    print("extra funding", h)
    case("S4N-v2-first-R-missing-required", "Negative control for R=1: k1 and k2 are members, but k4 (required) didn't sign",
         [(cell, "VR")], pay([cell], VR["lock"]),
         {"VR": {"config": VR, "signers": ["k1", "k2"]}})


def main():
    (HERE / "cases").mkdir(exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "--extra":
        extra()
        return
    build_real()
    if len(sys.argv) > 1 and sys.argv[1] == "--real-only":
        return
    h, cells = fund()
    (HERE / "data/devnet/funding.json").write_text(json.dumps({"funding_tx": h, "cells": cells}, indent=1))
    print("funding", h)
    build_synthetic(cells)


if __name__ == "__main__":
    main()
