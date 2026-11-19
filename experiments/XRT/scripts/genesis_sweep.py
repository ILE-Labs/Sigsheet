#!/usr/bin/env python3
"""XRT-1: which valid signature sets does each deployed multisig binary accept?

The attack considered: the genesis binary rejects a valid set when a member at position >= M signs. The genesis code
allocates `used_signatures[threshold]` and indexes it by member position (the 2024 fix sizes it by N,
background.md section 3), so such a member makes the lock read and write past the array; what happens depends
on the bytes there. This measures it on the local devnet, whose genesis multisig binary is byte-identical
to mainnet's (X1), with the node's own verifier (`test_tx_pool_accept`: full script verification, nothing
committed). Controls: the 2024 and v2 binaries (copied from mainnet, X1).

Per configuration (R = 0 unless noted): one funded cell; one unsigned spend; one signature per member
(the prototypes' signer); then many M-member sets, each written into the witness in member order (the order
Sigsheet's finalize writes) and, for some, in descending order; each set checked by the node.
A repeated key: a 2-of-3 whose script lists one key twice, spent by that one key's signature and its high-s twin.

Fresh test keys: keys/xrt/keys.json (outside the repository). Run from experiments/XRT/ with the devnet running:
    python3 -I -X utf8 scripts/genesis_sweep.py > results/genesis-sweep.json
"""
import json
import os
import pathlib
import random
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
INV = HERE.parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import core  # noqa: E402
import devnet  # noqa: E402
from core import c  # noqa: E402

KEYFILE = INV / "keys" / "xrt" / "keys.json"
CAP = 100 * devnet.CKB


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
        keys.append({"name": f"x{i}", "secret": c.b2h(secret), "blake160": c.b2h(c.blake160(c.pubkey_from_secret(secret)))})
    KEYFILE.write_text(json.dumps(keys, indent=1))
    os.chmod(KEYFILE, 0o600)
    return keys


POSITIONS = "--positions" in sys.argv  # run 3: larger N, one varying position per set


def configs():
    if POSITIONS:
        out = [("genesis", 0, m, n) for n in (13, 16, 20, 24) for m in (1, 2, 3, 5, 8, 10, 11, 12, 16) if m <= n]
        out += [("v2", 0, m, n) for n in (24,) for m in (1, 10)]
        return out
    out = []
    for n in range(2, 13):
        for m in range(1, n + 1):
            out.append(("genesis", 0, m, n))
    for dep in ("2024", "v2"):
        for n in (3, 5, 8, 12):
            for m in range(1, n + 1):
                out.append((dep, 0, m, n))
    for n, m in ((5, 3), (8, 4), (12, 6)):
        out.append(("genesis", 1, m, n))
    return out


def subsets(n, m, rng):
    if POSITIONS:  # the lowest m-1 positions plus one varying position j
        return sorted({tuple(sorted(set(range(m - 1)) | {j})) for j in range(m - 1, n)})
    sets = {tuple(range(m)), tuple(range(n - m, n))}
    allidx = list(range(n))
    for _ in range(12):
        sets.add(tuple(sorted(rng.sample(allidx, m))))
    return sorted(sets)


def main():
    keys = fresh_keys(24)
    rng = random.Random(20261119)
    plan = configs()
    locks = []
    for dep, r, m, n in plan:
        lock, cfg = devnet.multisig_lock(dep, r, m, [k["blake160"] for k in keys[:n]])
        locks.append((dep, r, m, n, lock, cfg))
    # a repeated key: a 2-of-3 that lists keys[0] twice
    dup_cfg = {"r": 0, "m": 2, "keys": [keys[0]["blake160"], keys[0]["blake160"], keys[1]["blake160"]]}
    dup_lock = {"code_hash": devnet.CODE["genesis"][0], "hash_type": devnet.CODE["genesis"][1],
                "args": core.config_id(dup_cfg)}
    dup_lock_v2 = {"code_hash": devnet.CODE["v2"][0], "hash_type": devnet.CODE["v2"][1], "args": core.config_id(dup_cfg)}

    outputs = [{"capacity": hex(CAP), "lock": L[4], "type": None} for L in locks]
    outputs += [{"capacity": hex(CAP), "lock": dup_lock, "type": None}, {"capacity": hex(CAP), "lock": dup_lock_v2, "type": None}]
    t0 = time.time()
    fund_hash, fund_tx = devnet.fund(outputs)
    prev_raw = core.raw_of(devnet.get_tx(fund_hash))
    report = {"funding_tx": fund_hash, "keys": "keys/xrt/keys.json (fresh, outside the repository)", "configs": [],
              "conditions": "local devnet, ckb 0.210.0; test_tx_pool_accept (full verification, not committed)"}
    k0 = devnet.KEYS["k0"]["blake160"]

    def spend(index, lock, cfg, dep):
        tx = {"version": "0x0", "cell_deps": [devnet.cell_dep(dep)], "header_deps": [],
              "inputs": [{"since": "0x0", "previous_output": {"tx_hash": fund_hash, "index": hex(index)}}],
              "outputs": [{"capacity": hex(CAP - devnet.FEE), "lock": devnet.sighash_lock(k0), "type": None}],
              "outputs_data": ["0x"], "witnesses": ["0x"]}
        # The lock's own message rule, computed with X1's implementation directly (the prototype's reader
        # refuses a config that lists a key twice, which is the point of this case, so it isn't used here).
        w0 = c.witness_args(core.script_of(cfg) + bytes(65 * cfg["m"]))
        return tx, c.multisig_message(tx, [0], [w0])

    def check(tx, lock_bytes):
        t = dict(tx)
        t["witnesses"] = [c.b2h(c.witness_args(lock_bytes))]
        res = devnet.try_rpc("test_tx_pool_accept", [t, "passthrough"])
        return res["ok"], (None if res["ok"] else res["error"][:160])

    for i, (dep, r, m, n, lock, cfg) in enumerate(locks):
        tx, msg = spend(i, lock, cfg, dep)
        sigs = [c.sign(msg, c.h2b(keys[j]["secret"])) for j in range(n)]
        script = core.script_of(cfg)
        rows = []
        for s in subsets(n, m, rng):
            if r and 0 not in s:
                continue  # first R must sign; not a valid set
            ok, err = check(tx, script + b"".join(sigs[j] for j in s))
            rows.append({"indices": list(s), "order": "member", "accepted": ok, "error": err})
            if max(s) >= m:
                ok2, err2 = check(tx, script + b"".join(sigs[j] for j in reversed(s)))
                rows.append({"indices": list(s), "order": "descending", "accepted": ok2, "error": err2})
        report["configs"].append({"deployment": dep, "r": r, "m": m, "n": n, "sets": rows})
        print(f"{dep:8s} R={r} M={m:2d} N={n:2d}: {sum(x['accepted'] for x in rows)}/{len(rows)} accepted", file=sys.stderr)

    # a repeated key: one key listed twice
    dup = {}
    if POSITIONS:
        report["repeated_key_2_of_3"] = "not run in --positions mode"
        report["seconds"] = round(time.time() - t0, 1)
        print(json.dumps(report, indent=1))
        return
    for name, lk, dep, idx in (("genesis", dup_lock, "genesis", len(locks)), ("v2", dup_lock_v2, "v2", len(locks) + 1)):
        tx, msg = spend(idx, lk, dup_cfg, dep)
        s0 = c.sign(msg, c.h2b(keys[0]["secret"]))
        twin = core.malleate(s0)
        script = core.script_of(dup_cfg)
        dup[name] = {
            "one_key_signature_and_its_twin": dict(zip(("accepted", "error"), check(tx, script + s0 + twin))),
            "one_key_and_the_other_member": dict(zip(("accepted", "error"), check(tx, script + s0 + c.sign(msg, c.h2b(keys[1]["secret"]))))),
        }
    report["repeated_key_2_of_3"] = dup
    report["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
