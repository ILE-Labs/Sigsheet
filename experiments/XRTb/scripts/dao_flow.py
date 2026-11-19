#!/usr/bin/env python3
"""XRTb-3: a Nervos DAO withdrawal of two deposits from one multisig, on the devnet.

A v2 2-of-3 multisig (fresh test keys, keys/xrtb/) deposits twice (blocks D1, D2), starts both withdrawals in
blocks W1 and W2 about 100 epochs apart (phase 1), and, once mature, withdraws both in one phase-2 transaction
whose header deps are [D1, D2, W1, W2]. For that transaction, the fee a reader shows is computed three ways and
compared with the fee the node itself reports (test_tx_pool_accept):
  naive      inputs minus outputs;
  v2-bound   design v2's rule: each DAO input's withdrawing header is unknown, so the largest accumulated rate
             among the header deps other than its deposit header is used (an upper bound);
  v3-proof   the candidate rule: each withdrawing cell's previous transaction comes with CKB's transaction
             proof (get_transaction_proof), verified offline against the block header's transactions_root, so
             the reader knows the withdrawing block exactly; also the minimal since (dao.c L202-L241);
A second phase-2 transaction with its output cut to the deposited capacity (the interest left as fee) is only
dry-run. Every DAO input's maximum withdraw is also read from the node (calculate_dao_maximum_withdraw).

Run from experiments/XRTb/ with the devnet running (about 10 minutes on a devnet with 10-block epochs):
    python3 -I -X utf8 scripts/dao_flow.py > results/dao-flow.json 2> results/dao-flow.log
"""
import hashlib
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
INV = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import core  # noqa: E402
import devnet  # noqa: E402
from core import c  # noqa: E402

KEYFILE = INV / "keys" / "xrtb" / "keys.json"
DAO_TYPE = {"code_hash": "0x82d76d1b75fe2fd9a27dfbaa65a039221a380d76c926f378d3f81cf3e7e13f2e", "hash_type": "type", "args": "0x"}
GENESIS_CELLBASE = "0x908a5f520f5dc59460b31b74b15628abce11c2360828d950590eef8994d4ab12"  # X1 genesis-info.json
DAO_DEP = {"out_point": {"tx_hash": GENESIS_CELLBASE, "index": "0x2"}, "dep_type": "code"}
FEE = 100_000
GAP_EPOCHS = 100  # between W1 and W2


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def keys_outside_checkout(path):
    """Test keys must never be written inside this repository: `keys` at its root must be a link to a folder
    outside it (for example `ln -s "$(mktemp -d)" keys`), which git ignores."""
    root = pathlib.Path(__file__).resolve().parents[3]
    p = pathlib.Path(path).resolve()
    if p == root or root in p.parents:
        raise SystemExit(f"refusing to write a key inside the checkout ({p}); make keys a link to a folder outside "
                         "it: ln -s \"$(mktemp -d)\" keys")
    return path


def fresh_keys(n):
    keys = json.loads(KEYFILE.read_text()) if KEYFILE.exists() else []
    if len(keys) >= n:
        return keys
    keys_outside_checkout(KEYFILE)
    KEYFILE.parent.mkdir(parents=True, exist_ok=True)
    for i in range(len(keys), n):
        while True:
            s = int.from_bytes(os.urandom(32), "big")
            if 0 < s < c.N:
                break
        secret = s.to_bytes(32, "big")
        keys.append({"name": f"y{i}", "secret": c.b2h(secret), "blake160": c.b2h(c.blake160(c.pubkey_from_secret(secret)))})
    KEYFILE.write_text(json.dumps(keys, indent=1))
    os.chmod(KEYFILE, 0o600)
    return keys


# ------------------------------------------------------------------ epochs, headers, proofs

def epoch_parts(e):
    return e & 0xFFFFFF, (e >> 24) & 0xFFFF, (e >> 40) & 0xFFFF


def epoch_enc(n, i, length):
    return n | (i << 24) | (length << 40)


def minimal_since(dep_epoch, wd_epoch):
    """dao.c L202-L241: the earliest absolute-epoch since for a phase-2 input."""
    dn, di, dl = epoch_parts(dep_epoch)
    wn, wi, wl = epoch_parts(wd_epoch)
    wf, df = wi * dl, di * wl
    assert wn > dn or (wn == dn and wf > df), "withdraw header must be after deposit header"
    deposited = wn - dn + (1 if wf > df else 0)
    lock = (deposited + 179) // 180 * 180
    assert lock >= 180
    return (0x20 << 56) | epoch_enc(dn + lock, di, dl)


def header(h):
    j = devnet.rpc("get_header", [h])
    raw = devnet.rpc("get_header", [h, "0x0"])
    dao = c.h2b(j["dao"])
    return {"hash": h, "number": int(j["number"], 16), "epoch": int(j["epoch"], 16), "ar": int.from_bytes(dao[8:16], "little"),
            "transactions_root": j["transactions_root"], "raw": raw}


def blake(b):
    return hashlib.blake2b(b, digest_size=32, person=c.PERSONAL).digest()


def cbmt_root(indices, lemmas, leaves):
    """merkle_cbt's MerkleProof::root, as CKB uses it (ckb-types utilities, CBMT with MergeByte32)."""
    if len(indices) != len(leaves) or not leaves:
        return None
    queue = sorted(zip(indices, leaves), key=lambda x: -x[0])
    lem = list(lemmas)
    while queue:
        index, node = queue.pop(0)
        if index == 0:
            return node if not lem and not queue else None
        sib_index = ((index + 1) ^ 1) - 1
        if queue and queue[0][0] == sib_index:
            sib = queue.pop(0)[1]
        elif lem:
            sib = lem.pop(0)
        else:
            return None
        parent = blake(node + sib) if index & 1 else blake(sib + node)
        queue.append(((index - 1) >> 1, parent))
    return None


def verify_tx_proof(tx_hash, proof, hdr):
    """True when the transaction is in the block whose header is hdr: CBMT root of the raw transaction hashes,
    then transactions_root = merge(raw root, witnesses_root)."""
    p = proof["proof"]
    raw_root = cbmt_root([int(i, 16) for i in p["indices"]], [c.h2b(x) for x in p["lemmas"]], [c.h2b(tx_hash)])
    if raw_root is None or proof["block_hash"] != hdr["hash"]:
        return False
    return c.b2h(blake(raw_root + c.h2b(proof["witnesses_root"]))) == hdr["transactions_root"]


def occupied(cell, data_len):
    def sb(s):
        return 32 + 1 + len(c.h2b(s["args"])) if s else 0
    return (8 + sb(cell["lock"]) + sb(cell.get("type")) + data_len) * devnet.CKB


def withdrawable(cell, data, ar_m, ar_n):
    co = occupied(cell, len(data))
    cap = int(cell["capacity"], 16)
    return (cap - co) * ar_n // ar_m + co


# ------------------------------------------------------------------ the transactions

def fund_dao(outputs, outputs_data):
    """devnet.fund, plus the DAO code as a cell dep (a deposit output's type script runs)."""
    key = devnet.KEYS["k0"]
    need = sum(int(o["capacity"], 16) for o in outputs) + devnet.FEE + 62 * devnet.CKB
    cells, total = devnet.mature_cells(key["blake160"], need)
    change = total - sum(int(o["capacity"], 16) for o in outputs) - devnet.FEE
    outs = outputs + [{"capacity": hex(change), "lock": devnet.sighash_lock(key["blake160"]), "type": None}]
    tx = {"version": "0x0", "cell_deps": [devnet.cell_dep("sighash"), DAO_DEP], "header_deps": [],
          "inputs": [{"since": "0x0", "previous_output": x["out_point"]} for x in cells],
          "outputs": outs, "outputs_data": list(outputs_data) + ["0x"], "witnesses": ["0x"] * len(cells)}
    devnet.sign_sighash_inputs(tx, key["secret"], list(range(len(cells))))
    h = devnet.rpc("send_transaction", [tx, "passthrough"])
    devnet.wait_committed(h)
    return h, tx


def sign_and_send(tx, prevs, lock, cfg, keys, send=True):
    model = core.Model(tx, prevs, {core.config_id(cfg): cfg}, {})
    gh = c.b2h(c.script_hash(lock))
    core.sign_group(model, gh, keys[0]["secret"])
    core.sign_group(model, gh, keys[1]["secret"])
    final = core.finalize(model)
    dry = devnet.try_rpc("test_tx_pool_accept", [final, "passthrough"])
    if not send:
        return final, dry, None
    if not dry["ok"]:
        raise RuntimeError(f"dry run refused: {dry['error'][:300]}")
    h = devnet.rpc("send_transaction", [final, "passthrough"])
    bh = devnet.wait_committed(h)
    return final, dry, (h, bh)


def wait_epoch(target_number):
    while True:
        e = devnet.rpc("get_current_epoch", [])
        n = int(e["number"], 16)
        if n >= target_number:
            return n
        log(f"epoch {n}, waiting for {target_number}")
        time.sleep(10)


def main():
    keys = fresh_keys(3)
    lock, cfg = devnet.multisig_lock("v2", 0, 2, [k["blake160"] for k in keys])
    deps = [devnet.cell_dep("v2"), DAO_DEP]
    rep = {"conditions": "local devnet, ckb 0.210.0, epoch length 10 blocks; fresh test keys keys/xrtb/ (outside the repository)",
           "multisig": {"deployment": "v2", "r": 0, "m": 2, "n": 3, "lock_args": lock["args"]}}
    deposits = []
    for cap in (2000, 3000):
        h, _ = fund_dao([{"capacity": hex(cap * devnet.CKB), "lock": lock, "type": DAO_TYPE},
                            {"capacity": hex(200 * devnet.CKB), "lock": lock, "type": None}],
                           outputs_data=["0x" + "00" * 8, "0x"])
        bh = devnet.rpc("get_transaction", [h])["tx_status"]["block_hash"]
        deposits.append({"tx": h, "block": bh, "capacity": cap})
        log("deposit", cap, h, bh)
    rep["deposits"] = deposits

    def phase1(d):
        dh = header(d["block"])
        prev = core.raw_of(devnet.get_tx(d["tx"]))
        tx = {"version": "0x0", "cell_deps": deps, "header_deps": [d["block"]],
              "inputs": [{"since": "0x0", "previous_output": {"tx_hash": d["tx"], "index": "0x0"}},
                         {"since": "0x0", "previous_output": {"tx_hash": d["tx"], "index": "0x1"}}],
              "outputs": [{"capacity": hex(d["capacity"] * devnet.CKB), "lock": lock, "type": DAO_TYPE},
                          {"capacity": hex(200 * devnet.CKB - FEE), "lock": lock, "type": None}],
              "outputs_data": [c.b2h(c.u64(dh["number"])), "0x"], "witnesses": ["0x", "0x"]}
        _, _, (h, bh) = sign_and_send(tx, {d["tx"]: prev}, lock, cfg, keys)
        log("phase 1", h, bh)
        return {"tx": h, "block": bh}

    w1 = phase1(deposits[0])
    e_now = int(devnet.rpc("get_current_epoch", [])["number"], 16)
    wait_epoch(e_now + GAP_EPOCHS)
    w2 = phase1(deposits[1])
    rep["phase1"] = [w1, w2]

    D = [header(d["block"]) for d in deposits]
    W = [header(w["block"]) for w in (w1, w2)]
    since = [minimal_since(D[i]["epoch"], W[i]["epoch"]) for i in range(2)]
    target = max(epoch_parts(s & ((1 << 56) - 1))[0] for s in since) + 1
    wait_epoch(target)

    prevs = {w["tx"]: core.raw_of(devnet.get_tx(w["tx"])) for w in (w1, w2)}
    header_deps = [D[0]["hash"], D[1]["hash"], W[0]["hash"], W[1]["hash"]]
    hdrs = {h["hash"]: h for h in D + W}
    node_max = [int(devnet.rpc("calculate_dao_maximum_withdraw", [{"tx_hash": deposits[i]["tx"], "index": "0x0"},
                                                                 {"tx_hash": (w1, w2)[i]["tx"], "index": "0x0"}]), 16)
                for i in range(2)]
    total = sum(node_max)

    def phase2(out_cap):
        return {"version": "0x0", "cell_deps": deps, "header_deps": header_deps,
                "inputs": [{"since": hex(since[i]), "previous_output": {"tx_hash": (w1, w2)[i]["tx"], "index": "0x0"}} for i in range(2)],
                "outputs": [{"capacity": hex(out_cap), "lock": lock, "type": None}], "outputs_data": ["0x"],
                "witnesses": [c.b2h(c.witness_args(None, c.u64(0), None)), c.b2h(c.witness_args(None, c.u64(1), None))]}

    # proofs of the two phase-1 transactions (the withdrawing cells' previous transactions)
    proofs = {w["tx"]: devnet.rpc("get_transaction_proof", [[w["tx"]], w["block"]]) for w in (w1, w2)}
    proof_ok = {h: verify_tx_proof(h, p, hdrs[p["block_hash"]]) for h, p in proofs.items()}
    # a forged proof: the right proof object, but claiming the deposit block
    forged = dict(proofs[w1["tx"]], block_hash=D[0]["hash"])
    forged_ok = verify_tx_proof(w1["tx"], forged, hdrs[D[0]["hash"]])

    def fee_rules(tx):
        outs = sum(int(o["capacity"], 16) for o in tx["outputs"])
        ins = naive_in = bound_in = proof_in = 0
        per = []
        for i, inp in enumerate(tx["inputs"]):
            op = inp["previous_output"]
            prev = prevs[op["tx_hash"]]
            cell, data = prev["outputs"][int(op["index"], 16)], c.h2b(prev["outputs_data"][int(op["index"], 16)])
            naive_in += int(cell["capacity"], 16)
            _, it, _ = c.parse_witness_args(c.h2b(tx["witnesses"][i]))
            dep = hdrs[tx["header_deps"][int.from_bytes(it, "little")]]
            assert dep["number"] == int.from_bytes(data, "little")
            cands = [hdrs[h] for h in tx["header_deps"] if h != dep["hash"]]
            b = withdrawable(cell, data, dep["ar"], max(x["ar"] for x in cands))
            p = proofs[op["tx_hash"]]
            assert verify_tx_proof(op["tx_hash"], p, hdrs[p["block_hash"]])
            wd = hdrs[p["block_hash"]]
            e = withdrawable(cell, data, dep["ar"], wd["ar"])
            bound_in += b
            proof_in += e
            per.append({"input": i, "capacity": int(cell["capacity"], 16), "candidates": len(cands), "v2_bound": b, "v3_proof": e,
                        "node_max_withdraw": node_max[i],
                        "minimal_since_from_proof": hex(minimal_since(dep["epoch"], wd["epoch"])), "since_in_tx": inp["since"]})
        return {"naive": naive_in - outs, "v2_bound": bound_in - outs, "v3_proof": proof_in - outs,
                "per_input": per}

    tx_ok = phase2(total - FEE)
    tx_cut = phase2(deposits[0]["capacity"] * devnet.CKB + deposits[1]["capacity"] * devnet.CKB - FEE)
    rules_ok, rules_cut = fee_rules(tx_ok), fee_rules(tx_cut)
    final_cut, dry_cut, _ = sign_and_send(tx_cut, prevs, lock, cfg, keys, send=False)
    final_ok, dry_ok, sent = sign_and_send(tx_ok, prevs, lock, cfg, keys, send=True)
    rep["phase2"] = {
        "header_deps": header_deps, "tx": sent[0], "block": sent[1],
        "node_fee_test_tx_pool_accept": int(dry_ok["result"]["fee"], 16), "cycles": dry_ok["result"]["cycles"],
        "fees_by_rule": rules_ok, "proofs_verify_offline": proof_ok, "forged_block_hash_with_real_proof_verifies": forged_ok,
        "transaction_proofs": proofs,
    }
    rep["phase2_cut_output"] = {"dry_run": dry_cut["ok"], "node_fee_test_tx_pool_accept": int(dry_cut["result"]["fee"], 16) if dry_cut["ok"] else None,
                                "error": None if dry_cut["ok"] else dry_cut["error"][:200], "fees_by_rule": rules_cut}
    rep["headers"] = {h["hash"]: {k: h[k] for k in ("number", "epoch", "ar")} for h in D + W}
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
