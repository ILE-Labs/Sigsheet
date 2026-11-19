#!/usr/bin/env python3
"""XRTb-1: the genesis binary with a required member at position 10, and a set no order can fix.

The objection considered: the finalizer's genesis rule breaks (a) when position 10 is required by require_first_n (R = 11)
and (b) when only M members signed and one of them is at position 10. XRT-1 measured R = 0 only. Here, on the
local devnet (genesis binary byte-identical to mainnet's), with the node's own verifier (test_tx_pool_accept,
nothing committed), each set is written in member order and, where it differs, in descending order:
  A. N = 12, M = 11, R = 11: members 0-10 (position 10 required; M >= 11).
  B. N = 12, M = 2,  R = 0:  {5, 10} (both orders), {10, 11} (both orders), {5, 11}.
  C. N = 12, M = 10, R = 10: members 0-9; and N = 12, M = 11, R = 0: {0-9, 11}.
Fresh test keys: keys/xrt/keys.json (XRT-1's, outside the repository). Run from experiments/XRTb/ with the devnet running:
    python3 -I -X utf8 scripts/genesis_r.py > results/genesis-r.json
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
INV = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import core  # noqa: E402
import devnet  # noqa: E402
from core import c  # noqa: E402

KEYS = json.loads((INV / "keys" / "xrt" / "keys.json").read_text())
CAP = 100 * devnet.CKB
PLAN = [
    ("A", 11, 11, 12, [tuple(range(11))]),
    ("B", 0, 2, 12, [(5, 10), (10, 11), (5, 11)]),
    ("C1", 10, 10, 12, [tuple(range(10))]),
    ("C2", 0, 11, 12, [tuple(list(range(10)) + [11])]),
]


def main():
    locks = []
    for name, r, m, n, sets in PLAN:
        lock, cfg = devnet.multisig_lock("genesis", r, m, [k["blake160"] for k in KEYS[:n]])
        locks.append((name, r, m, n, sets, lock, cfg))
    fund_hash, _ = devnet.fund([{"capacity": hex(CAP), "lock": L[5], "type": None} for L in locks])
    k0 = devnet.KEYS["k0"]["blake160"]
    rep = {"funding_tx": fund_hash, "conditions": "local devnet, ckb 0.210.0; test_tx_pool_accept (nothing committed)", "configs": []}
    for i, (name, r, m, n, sets, lock, cfg) in enumerate(locks):
        tx = {"version": "0x0", "cell_deps": [devnet.cell_dep("genesis")], "header_deps": [],
              "inputs": [{"since": "0x0", "previous_output": {"tx_hash": fund_hash, "index": hex(i)}}],
              "outputs": [{"capacity": hex(CAP - devnet.FEE), "lock": devnet.sighash_lock(k0), "type": None}],
              "outputs_data": ["0x"], "witnesses": ["0x"]}
        msg = c.multisig_message(tx, [0], [c.witness_args(core.script_of(cfg) + bytes(65 * m))])
        sigs = [c.sign(msg, c.h2b(KEYS[j]["secret"])) for j in range(n)]
        rows = []
        for s in sets:
            for order, seq in (("member", s), ("descending", tuple(reversed(s)))):
                if order == "descending" and len(s) < 2:
                    continue
                t = dict(tx)
                t["witnesses"] = [c.b2h(c.witness_args(core.script_of(cfg) + b"".join(sigs[j] for j in seq)))]
                res = devnet.try_rpc("test_tx_pool_accept", [t, "passthrough"])
                rows.append({"indices": list(s), "order": order, "accepted": res["ok"], "error": None if res["ok"] else res["error"][:160]})
        rep["configs"].append({"case": name, "deployment": "genesis", "r": r, "m": m, "n": n, "sets": rows})
        print(name, [(x["indices"], x["order"], x["accepted"]) for x in rows], file=sys.stderr)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
