#!/usr/bin/env python3
"""X3a step 3: check every CCC aggregation result against the multisig lock's rules, and count outcomes.

Usage, from experiments/X3a:  python3 -I -X utf8 scripts/analyze_ccc.py > results/ccc-analysis.json

For each of the 120 orders in results/ccc-orders.json: the witness lock must be exactly 4 + 20N + 65M bytes;
its M signatures must recover (over the group's message, recomputed independently) to M distinct members,
with the first R among them (the lock's rule, background.md section 1). Then counts how many distinct multisig
witnesses and whole witness lists the 120 orders produced, which member sets CCC kept, and in how many
orders the single-key input's signature survived.
"""
import collections
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "X1" / "scripts"))
import ckbcore as c  # noqa: E402

d = json.loads((HERE / "results" / "partials.json").read_text())
runs = json.loads((HERE / "results" / "ccc-orders.json").read_text())["runs"]
msg = c.h2b(d["message"])
members = [c.h2b(k) for k in d["members"]]
M, R, N = d["threshold"], d["require_first_n"], len(members)


def lock_valid(witness_hex):
    lock = c.parse_witness_args(c.h2b(witness_hex))[0]
    if len(lock) != 4 + 20 * N + 65 * M:
        return False, "size"
    used = []
    for i in range(M):
        sig = lock[4 + 20 * N + 65 * i: 4 + 20 * N + 65 * (i + 1)]
        try:
            kh = c.blake160(c.recover(msg, sig))
        except ValueError:
            return False, f"slot {i} doesn't recover"
        if kh not in members or members.index(kh) in used:
            return False, f"slot {i} isn't an unused member"
        used.append(members.index(kh))
    if any(i not in used for i in range(R)):
        return False, "first R missing"
    return True, sorted(used)


valid = collections.Counter()
kept_sets = collections.Counter()
for r in runs:
    ok, info = lock_valid(r["witness0"])
    valid[ok] += 1
    kept_sets[",".join(map(str, sorted(r["kept_members"])))] += 1
out = {
    "orders": len(runs),
    "all_results_valid_under_the_lock_rule": valid[True] == len(runs),
    "valid_count": valid[True],
    "distinct_multisig_witnesses": len({r["witness0"] for r in runs}),
    "distinct_witness_lists": len({(r["witness0"], r["witness1"]) for r in runs}),
    "kept_member_sets": dict(sorted(kept_sets.items())),
    "kept_set_equals_first_three_in_order": sum(sorted(r["kept_members"]) == sorted(r["order"][:3]) for r in runs),
    "single_key_signature_kept_in_orders": sum(r["single_key_signature_kept"] for r in runs),
    "single_key_kept_exactly_when_its_file_is_first": all(
        r["single_key_signature_kept"] == (r["order"][0] == d["single_key_owner_member"]) for r in runs),
    "tx_hash_unchanged_in_all": all(r["tx_hash_unchanged"] for r in runs),
    "signatures_beyond_M_kept_anywhere": 0,  # an M-slot lock has no room for them
}
json.dump(out, sys.stdout, indent=1)
