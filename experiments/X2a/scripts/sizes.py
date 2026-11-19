#!/usr/bin/env python3
"""X2a: the bytes every format must carry for the two real cases, in binary and in hex JSON.

Usage, from experiments/X2a:  python3 -I -X utf8 scripts/sizes.py > results/sizes.json

For fiber-scripts PR #34 (the 3-of-5 v2 deploy, transaction 0x4396de69…92ee) and the genesis 2-of-3 payment (2-of-3
genesis, 0x63a7f3a5…baa4), from X1's saved mainnet data:
- the transaction: Molecule `Transaction` (raw + witnesses) and compact RPC JSON (hex numbers and bytes,
  no whitespace, as RFC 8785 would emit it);
- every previous transaction the inputs spend (deduplicated), in two like-for-like pairs: with its witnesses
  (Molecule `Transaction` against compact RPC JSON) and without them (Molecule `RawTransaction` against the
  same JSON with the `witnesses` field left out). The raw part alone is all a signer needs to check an out
  point, since the hash covers the raw transaction (background.md section 2). The hash of each is checked;
- the data of the cells the transaction spends (what path A's `resolved_inputs.outputs_data` would repeat);
- the output data the transaction itself carries.
Every Molecule encoding uses X1's independent encoder (experiments/X1/scripts/ckbcore.py), and each raw
transaction's hash is recomputed and compared, so the bytes measured are the bytes that hash correctly.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
X1 = HERE.parent / "X1"
sys.path.insert(0, str(X1 / "scripts"))
import ckbcore as c  # noqa: E402


def full_tx(tx):
    return c.table([c.raw_transaction(tx), c.dynvec([c.mol_bytes(c.h2b(w)) for w in tx["witnesses"]])])


def compact(o):
    return len(json.dumps(o, separators=(",", ":")))


def data_bytes(datas):
    return sum((len(x) - 2) // 2 for x in datas)


def mainnet_tx(h):
    d = json.loads((X1 / "data" / "mainnet" / f"{h}.json").read_text())
    return d["result"]["transaction"]


deploy = json.loads((X1 / "data" / "fiber-scripts-34" / "mainnet.json").read_text())
cases = {
    "R1-fiber-scripts-pr34": (json.loads((X1 / "cases" / "R1-fiber-scripts-pr34.json").read_text()),
                              lambda h: deploy["used_input_txs"][h]),
    "R2-dao-payout": (json.loads((X1 / "cases" / "R2-dao-payout.json").read_text()), mainnet_tx),
}
out = {}
for name, (case, prev_of) in cases.items():
    tx = case["tx"]
    assert c.b2h(c.tx_hash(tx)) == case["tx_hash"]
    prev_hashes = sorted({i["previous_output"]["tx_hash"] for i in tx["inputs"]})
    prevs = {}
    for h in prev_hashes:
        p = prev_of(h)
        p = {k: p[k] for k in ("version", "cell_deps", "header_deps", "inputs", "outputs", "outputs_data", "witnesses")}
        assert c.b2h(c.tx_hash(p)) == h, f"previous transaction {h} doesn't hash to its out point"
        prevs[h] = {
            "molecule_transaction": len(full_tx(p)),
            "molecule_raw_transaction_only": len(c.raw_transaction(p)),
            "json_compact": compact(p),
            "json_compact_without_witnesses": compact({k: v for k, v in p.items() if k != "witnesses"}),
            "outputs_data_bytes": data_bytes(p["outputs_data"]),
            "witnesses_bytes": data_bytes(p["witnesses"]),
        }
    spent = data_bytes([ic["data"] for ic in case["input_cells"]])
    t = {"molecule_transaction": len(full_tx(tx)), "json_compact": compact(tx),
         "outputs_data_bytes": data_bytes(tx["outputs_data"])}
    # Like for like: the transaction itself is always whole (its witnesses carry the signatures); the proof is
    # either whole on both sides or raw only (no witnesses) on both sides.
    bin_with = t["molecule_transaction"] + sum(v["molecule_transaction"] for v in prevs.values())
    json_with = t["json_compact"] + sum(v["json_compact"] for v in prevs.values())
    bin_raw = t["molecule_transaction"] + sum(v["molecule_raw_transaction_only"] for v in prevs.values())
    json_raw = t["json_compact"] + sum(v["json_compact_without_witnesses"] for v in prevs.values())
    out[name] = {
        "transaction": t,
        "previous_transactions": prevs,
        "spent_cells_data_bytes": spent,
        "tx_plus_proof_with_proof_witnesses": {"binary": bin_with, "hex_json": json_with,
                                               "hex_json_over_binary_bytes": json_with - bin_with,
                                               "ratio": round(json_with / bin_with, 3)},
        "tx_plus_proof_raw_only": {"binary": bin_raw, "hex_json": json_raw,
                                   "hex_json_over_binary_bytes": json_raw - bin_raw,
                                   "ratio": round(json_raw / bin_raw, 3)},
        "previous_witness_bytes_a_raw_only_proof_saves": sum(v["molecule_transaction"] - v["molecule_raw_transaction_only"] for v in prevs.values()),
    }
json.dump({"measured": "2026-11-18", "cases": out}, sys.stdout, indent=1)
