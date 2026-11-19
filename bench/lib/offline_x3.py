"""X3 offline: merging in any order, on synthetic copies of X3's three devnet cases.

The recorded run (experiments/X3) built S10, S11 and R1-35 from cells funded on a local devnet and signed them
with test keys kept outside the repository. Here the same three shapes are built offline: the multisig members
are fresh keys made at run time (never written anywhere), and the spent cells come from one synthetic previous
transaction, hashed like a real one, so the files' proofs by hash still check. Everything else is X3's own code
(experiments/X3/scripts/x3.py: the pools, the three merge orders, the checks), with its fixed seed.
"""
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXP = ROOT / "experiments"
sys.path.insert(0, str(EXP / "prototypes"))
sys.path.insert(0, str(EXP / "X3" / "scripts"))
import core  # noqa: E402
import devnet  # noqa: E402
from core import c  # noqa: E402


def fresh_keys(names):
    keys = {}
    for name in names:
        sec = os.urandom(32)
        keys[name] = {"name": name, "secret": c.b2h(sec), "blake160": c.b2h(c.blake160(c.pubkey_from_secret(sec)))}
    return keys


def synthetic_funding(keys):
    """The configurations X3 spends (X5's fund_s4.py names), all cells in one synthetic previous transaction."""
    plan = [("A23G", "genesis", 0, 2, ["s1", "s2", "s3"], None, 4),
            ("A23V", "v2", 0, 2, ["s1", "s2", "s3"], None, 5),
            ("A23VS", "v2", 0, 2, ["s1", "s2", "s3"], 100, 1),
            ("B35VR", "v2", 1, 3, ["s1", "s2", "s3", "s4", "s5"], None, 1)]
    outputs, configs = [], {}
    for name, dep, r, m, members, since, n in plan:
        lock, cfg = devnet.multisig_lock(dep, r, m, [keys[k]["blake160"] for k in members], since)
        configs[name] = {"deployment": dep, "lock": lock, "config": cfg, "since_in_args": since, "cells": []}
        for _ in range(n):
            configs[name]["cells"].append(len(outputs))
            outputs.append({"capacity": hex(2000 * devnet.CKB), "lock": lock, "type": None})
    prev = {"version": "0x0", "cell_deps": [devnet.cell_dep("sighash")], "header_deps": [],
            "inputs": [{"since": "0x0", "previous_output": {"tx_hash": c.b2h(os.urandom(32)), "index": "0x0"}}],
            "outputs": outputs, "outputs_data": ["0x"] * len(outputs), "witnesses": []}
    h = c.b2h(c.tx_hash(prev))
    for e in configs.values():
        e["cells"] = [{"tx_hash": h, "index": hex(i)} for i in e["cells"]]
    return {"funding_tx": h, "configs": configs}, {h: prev}


def run(trials, include_r1):
    keys = fresh_keys(["s1", "s2", "s3", "s4", "s5", "s6"])
    devnet.KEYS.clear()
    devnet.KEYS.update(keys)
    funding, prevs = synthetic_funding(keys)
    devnet.funding = lambda: funding
    devnet.get_tx = lambda h: prevs[h]
    argv, sys.argv = sys.argv, ["x3.py"]  # x3 reads its trial count from the command line at import
    try:
        import x3  # noqa: E402  (after the keys exist: x3 reads s6 at import)
    finally:
        sys.argv = argv
    cases = {}
    if include_r1:
        cases["R1-fiber-scripts-pr34"] = x3.load_case("R1-fiber-scripts-pr34.json")
    cases["S6-two-multisig-groups"] = x3.load_case("S6-two-multisig-groups.json")
    cases["S7-multisig-plus-single-key"] = x3.load_case("S7-multisig-plus-single-key.json")
    dn = x3.devnet_cases()
    cases.update(dn)
    out = {"cases": {}}
    for name, m in cases.items():
        n = max(20, trials // 4) if name.startswith("R1-fiber") else trials
        out["cases"][name] = x3.run_case(name, m, n)
        print("  X3", name, "done", file=sys.stderr, flush=True)
    s10 = dn["S10-same-script-two-deployments"]
    groups = core.lock_groups(s10)
    by_args = {}
    for gh, es in s10.sigs.items():
        by_args.setdefault(groups[gh]["lock"]["args"], []).extend(es.values())
    out["S10_keyed_by_args"] = sorted(len(v) for v in by_args.values())
    out["S10_keyed_by_lock_hash"] = sorted(len(v) for v in s10.sigs.values())
    fr, final = x3.first_r_check(dn["R1-35-first-member-required"])
    out["first_r"] = fr
    out["finals_pass_lock_rules"] = {name: all(core.lock_rule_check(core.finalize(m), m.prevs).values())
                                     for name, m in dn.items()}
    keys.clear()
    devnet.KEYS.clear()
    return out


if __name__ == "__main__":
    print(json.dumps(run(int(sys.argv[1]) if len(sys.argv) > 1 else 200, len(sys.argv) > 2), indent=1))
