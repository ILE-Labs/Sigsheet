#!/usr/bin/env python3
"""X4 part 1: does each deployed multisig lock accept a malleated (high-s) signature? Run on the devnet.

Usage, from experiments/X4:  python3 -I -X utf8 scripts/high_s_devnet.py > results/high-s-devnet.json

X3a found by reading the code that the lock's secp256k1 doesn't reject high-s signatures; this runs it on the
devnet, because the case against BIP-174's and PCZT's merge rules leans on it.
For each deployment (genesis, 2024, v2), on a fresh 2-of-3 cell [s1, s2, s3]:
- control: both signatures low-s (as every wallet makes them): test_tx_pool_accept;
- twin: s1's signature replaced by its malleated twin (s -> N - s, recovery bit flipped), which recovers to the
  same key over the same message: test_tx_pool_accept, then send_transaction and wait until committed;
- both twins (a second cell would be needed to commit; dry run only).
The devnet runs the genesis binary bundled with ckb (byte-identical to mainnet's) and the 2024 and v2 binaries
copied from mainnet (X1's Devnet row).
"""
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import core  # noqa: E402
import devnet  # noqa: E402
from core import c  # noqa: E402

CELLS = {"genesis": ("A23G", 0), "2024": ("A23B", 0), "v2": ("A23V", 1)}


def lock_sigs(final, gi):
    lock, it, ot = c.parse_witness_args(c.h2b(final["witnesses"][gi]))
    return lock, it, ot


def with_twins(final, gi, which):
    """Replace the signatures at the given positions of the lock with their high-s twins."""
    t = json.loads(json.dumps(final))
    lock, it, ot = lock_sigs(t, gi)
    n = lock[3]
    body = bytearray(lock)
    for j in which:
        start = 4 + 20 * n + 65 * j
        body[start:start + 65] = core.malleate(bytes(lock[start:start + 65]))
    t["witnesses"][gi] = c.b2h(c.witness_args(bytes(body), it, ot))
    return t


def main():
    out = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "rpc": devnet.RPC, "runs": {}}
    s6 = devnet.sighash_lock(devnet.KEYS["s6"]["blake160"])
    for dep, (name, n) in CELLS.items():
        m = devnet.spend_model([(name, n)], [(s6, 999 * devnet.CKB)])
        gh = devnet.group_of(m, name)
        core.sign_group(m, gh, devnet.secret("s1"))
        core.sign_group(m, gh, devnet.secret("s2"))
        final = core.finalize(m)
        gi = core.lock_groups(m)[gh]["inputs"][0]
        lock, _, _ = lock_sigs(final, gi)
        n_keys = lock[3]
        s_values = [int.from_bytes(lock[4 + 20 * n_keys + 65 * j + 32: 4 + 20 * n_keys + 65 * j + 64], "big")
                    for j in range(lock[2])]
        r = {"cell": m.tx["inputs"][0]["previous_output"], "tx_hash": c.b2h(c.tx_hash(final)),
             "low_s_signatures": all(s <= core.N_HALF for s in s_values)}
        r["control_low_s_dry_run"] = devnet.try_rpc("test_tx_pool_accept", [final, "passthrough"])
        twin = with_twins(final, gi, [0])
        lock_t, _, _ = lock_sigs(twin, gi)
        st = int.from_bytes(lock_t[4 + 20 * n_keys + 32: 4 + 20 * n_keys + 64], "big")
        r["twin_is_high_s"] = st > core.N_HALF
        r["twin_passes_python_lock_rules"] = all(core.lock_rule_check(twin, m.prevs).values())
        r["both_twins_dry_run"] = devnet.try_rpc("test_tx_pool_accept", [with_twins(final, gi, [0, 1]), "passthrough"])
        r["twin_dry_run"] = devnet.try_rpc("test_tx_pool_accept", [twin, "passthrough"])
        if r["twin_dry_run"]["ok"]:
            sent = devnet.try_rpc("send_transaction", [twin, "passthrough"])
            r["twin_sent"] = sent
            if sent["ok"]:
                r["twin_committed_in_block"] = devnet.rpc("get_block", [devnet.wait_committed(sent["result"])])["header"]["number"]
                committed = devnet.get_tx(sent["result"])
                r["committed_witness_equals_twin"] = committed["witnesses"][gi] == twin["witnesses"][gi]
        out["runs"][dep] = r
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
