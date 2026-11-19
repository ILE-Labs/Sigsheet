#!/usr/bin/env python3
"""Build the internal model of every real and X1 synthetic case, from the cases' own files.

Usage, from experiments/prototypes:  python3 -I -X utf8 cases.py
Writes ../X2/cases/<id>.json: {"id", "source", "model": {tx, prevs, configs, sigs}, "expected": {...}}.

- R1, fiber-scripts PR #34: replayed from the real deploy file (X1's copy of mainnet.json, SHA-256 checked by X1):
  `cell_tx` is the transaction; `used_input_txs` proves its inputs; `deployment.multisig_config` gives the
  members (its `lock_code_hash` is ignored: the lock kind comes from the input cell); the signatures are the
  file's `cell_tx_signatures` plus the four PR comments, exactly as pasted.
- R2, the genesis 2-of-3 payment: the committed mainnet transaction and its previous transaction (X1's RPC records); the
  signatures are the two in the committed witness.
- S1-S9 and S4N, X1's devnet cases: X1's case file, the funding transaction (X1's record, or the devnet's RPC for
  S4N's), and the signatures from the committed transaction (S4N: from X1's ckb-cli file, which holds the
  three signatures X1 used).
Every expected message is X1's (results/python.json); the model must reproduce it (X2 checks).
"""
import json
import pathlib
import re
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core  # noqa: E402
from core import c  # noqa: E402

X1 = HERE.parent / "X1"
OUT = HERE.parent / "X2" / "cases"
RPC = "http://127.0.0.1:8114/"
MSGS = json.loads((X1 / "results" / "python.json").read_text())["messages"]
MAINNET_GENESIS = "0x92b197aa1fba0f63633922c61c92375c9c074a93e85963554f5499fe1450d0e5"
DEVNET_GENESIS = json.loads((X1 / "data" / "devnet" / "genesis-info.json").read_text())["genesis_hash"]


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(out["error"])
    return out["result"]


# ------------------------------------------------------------------ bech32m full-format address -> args

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def address_args(addr):
    hrp, data = addr.split("1", 1)
    vals = [_CHARSET.index(ch) for ch in data]
    assert c._polymod(c._hrp_expand(hrp) + vals) == 0x2BC830A3, "bad bech32m checksum"
    payload = bytes(c._convertbits(vals[:-6], 5, 8, pad=False))
    assert payload[0] == 0, "not a full-format address"
    code_hash, hash_type, args = payload[1:33], payload[33], payload[34:]
    assert c.b2h(code_hash) == core.SIGHASH[0] and hash_type == 1, "not a single-key address"
    return c.b2h(args)


# ------------------------------------------------------------------ helpers

def build(case_id, source, tx_final_or_template, prevs, configs, sig_list, network_genesis, extra=None):
    """sig_list: [(any 65-byte signature hex)], filed under the group and key that recover it."""
    probe = core.Model(tx_final_or_template, prevs, configs, {})
    groups = core.lock_groups(probe)
    model = core.Model(core.template_from_final(tx_final_or_template, groups), prevs, configs, {})
    unplaced = []
    for sig in sig_list:
        placed = False
        for gh, g in groups.items():
            if g["kind"] == "unknown":
                continue
            kh = core.signer_of(model, g, c.h2b(sig))
            if kh:
                core.add_sig(model.sigs, gh, kh, c.h2b(sig))
                placed = True
        if not placed:
            unplaced.append(sig)
    warnings = core.validate(model)
    exp_msgs = {}
    for gh, g in groups.items():
        if g["kind"] in ("multisig", "sighash"):
            exp_msgs[gh] = c.b2h(core.group_message(model, g))
    x1 = MSGS.get(case_id, {})
    doc = {
        "id": case_id, "source": source, "network_genesis_hash": network_genesis,
        "model": {"tx": model.tx, "prevs": model.prevs, "configs": model.configs, "sigs": model.sigs},
        "expected": {"tx_hash": c.b2h(c.tx_hash(model.tx)), "x1_messages": x1,
                     "model_messages": exp_msgs, "unplaced_signatures": unplaced, "warnings": warnings,
                     "status": core.status(model)},
    }
    if extra:
        doc["expected"].update(extra)
    # X1's messages are keyed by group name; every one of them must appear among the model's.
    missing = [m for m in x1.values() if m not in exp_msgs.values()]
    doc["expected"]["x1_messages_reproduced"] = not missing
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{case_id}.json").write_text(json.dumps(doc, indent=1, sort_keys=True))
    return doc


def raw(tx):
    return core.raw_of(tx)


def mainnet_tx(h):
    return json.loads((X1 / "data" / "mainnet" / f"{h}.json").read_text())["result"]["transaction"]


# ------------------------------------------------------------------ R1: fiber-scripts PR #34, from the deploy file

def r1():
    d = json.loads((X1 / "data" / "fiber-scripts-34" / "mainnet.json").read_text())
    tx = d["cell_tx"]
    prevs = {}
    for i in tx["inputs"]:
        h = i["previous_output"]["tx_hash"]
        prevs[h] = raw(d["used_input_txs"][h])
    mc = d["deployment"]["multisig_config"]
    cfg = {"r": mc["require_first_n"], "m": mc["threshold"], "keys": [address_args(a) for a in mc["sighash_addresses"]]}
    configs = {core.config_id(cfg): cfg}
    sigs = [s for v in d["cell_tx_signatures"].values() for s in v]
    for n in range(1, 5):
        text = (X1 / "data" / "fiber-scripts-34" / f"comment-{n}.txt").read_text()
        sigs += re.findall(r"0x[0-9a-f]{40,56}:\s*(0x[0-9a-f]{130})", text)
    return build("R1-fiber-scripts-pr34", "fiber-scripts PR #34 deploy file (cell_tx, used_input_txs, "
                 "multisig_config, cell_tx_signatures) and the four PR comments", tx, prevs, configs, sigs,
                 MAINNET_GENESIS, {"declared_lock_code_hash_ignored": mc["lock_code_hash"]})


# ------------------------------------------------------------------ R2: the genesis 2-of-3 payment, committed on mainnet

def r2():
    h = "0x63a7f3a52fc91c52939186ca9c1064238ccdfe498d3398f25707537f591bbaa4"
    tx = mainnet_tx(h)
    tx = {k: tx[k] for k in core.RAW_FIELDS + ("witnesses",)}
    prevs = {i["previous_output"]["tx_hash"]: raw(mainnet_tx(i["previous_output"]["tx_hash"])) for i in tx["inputs"]}
    lock, _, _ = c.parse_witness_args(c.h2b(tx["witnesses"][0]))
    info = c.parse_multisig_script(lock)
    cfg = {"r": info["require_first_n"], "m": info["threshold"], "keys": [c.b2h(k) for k in info["keys"]]}
    n = len(info["keys"])
    sigs = [c.b2h(lock[4 + 20 * n + 65 * j: 4 + 20 * n + 65 * (j + 1)]) for j in range(info["threshold"])]
    return build("R2-dao-payout", "mainnet transaction 0x63a7f3a5...baa4 and its previous transaction (X1's RPC "
                 "records); signatures from the committed witness", tx, prevs, {core.config_id(cfg): cfg}, sigs,
                 MAINNET_GENESIS, {"committed_final_tx_hash": h})


# ------------------------------------------------------------------ X1's devnet cases

def devnet_prev(h):
    f = X1 / "data" / "devnet" / f"{h}.json"
    if f.exists():
        return raw(json.loads(f.read_text())["result"]["transaction"])
    cache = OUT.parent / "data" / f"{h}.json"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        res = rpc("get_transaction", [h])
        cache.write_text(json.dumps({"rpc": RPC, "method": "get_transaction", "result": res}, indent=1))
    return raw(json.loads(cache.read_text())["result"]["transaction"])


def x1_case(case_id):
    case = json.loads((X1 / "cases" / f"{case_id}.json").read_text())
    tx = case["tx"]
    prevs = {i["previous_output"]["tx_hash"]: devnet_prev(i["previous_output"]["tx_hash"]) for i in tx["inputs"]}
    configs = {}
    for g in case["groups"]:
        if g["kind"] == "multisig":
            cfg = {"r": g["multisig"]["require_first_n"], "m": g["multisig"]["threshold"],
                   "keys": g["multisig"]["key_hashes"]}
            configs[core.config_id(cfg)] = cfg
    sigs, extra = [], {}
    committed = X1 / "data" / "devnet" / "committed" / f"{case_id}.json"
    if committed.exists():
        final = json.loads(committed.read_text())["result"]["transaction"]
        extra["committed_final_tx_hash"] = final["hash"]
        for w in final["witnesses"]:
            b = c.h2b(w)
            if not b:
                continue
            try:
                lock, _, _ = c.parse_witness_args(b)
            except ValueError:
                continue
            if lock is None:
                continue
            if len(lock) == 65:
                sigs.append(c.b2h(lock))
            elif lock[0] == 0 and len(lock) >= 4:
                n, m = lock[3], lock[2]
                if len(lock) == 4 + 20 * n + 65 * m:
                    sigs += [c.b2h(lock[4 + 20 * n + 65 * j: 4 + 20 * n + 65 * (j + 1)]) for j in range(m)]
    else:
        # S4N: X1's negative control. Its ckb-cli file "-threshold" holds the three signatures X1 made (k4, k1,
        # k2); the case is "the required first member didn't sign", so only the two others are kept.
        f = X1 / "results" / "ckb-cli" / f"{case_id}-threshold.json"
        if f.exists():
            for v in json.loads(f.read_text())["signatures"].values():
                sigs += v
            g = [g for g in case["groups"] if g["kind"] == "multisig"][0]
            required = set(g["multisig"]["key_hashes"][: g["multisig"]["require_first_n"]])
            probe = core.Model(core.template_from_final(tx, core.lock_groups(core.Model(tx, prevs, configs, {}))),
                               prevs, configs, {})
            pg = list(core.lock_groups(probe).values())[0]
            kept = [s for s in sigs if core.signer_of(probe, pg, c.h2b(s)) not in required]
            extra["signatures_left_out"] = "the required member's (first R), to make the negative case"
            extra["signatures_in_x1_file"] = len(sigs)
            sigs = kept
    return build(case_id, f"X1 case file cases/{case_id}.json; previous transactions from X1's devnet record; "
                 "signatures from the committed transaction", tx, prevs, configs, sigs, DEVNET_GENESIS, extra)


def main():
    docs = [r1(), r2()]
    for f in sorted((X1 / "cases").glob("S*.json")):
        docs.append(x1_case(f.stem))
    for d in docs:
        e = d["expected"]
        n_sigs = sum(len(v) for v in d["model"]["sigs"].values())
        print(f"{d['id']:<36} groups={len(e['model_messages'])} sigs={n_sigs} "
              f"x1_reproduced={e['x1_messages_reproduced']} unplaced={len(e['unplaced_signatures'])} "
              f"warnings={len(e['warnings'])}")


if __name__ == "__main__":
    main()
