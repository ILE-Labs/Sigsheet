#!/usr/bin/env python3
"""X3a step 4: property tests of four merge rules, on PR #34's real signatures plus junk.

Usage, from experiments/X3a:  python3 -I -X utf8 scripts/merge_rules.py [trials] > results/merge-rules.json

The pool for the 3-of-5 multisig group of PR #34 (message recomputed in step 1):
- the five real member signatures;
- each one's malleated twin: s replaced by N - s and the recovery bit flipped. It recovers to the same key
  over the same message, with different bytes (standard ECDSA malleability);
- junk: 65 random bytes; a valid signature over the same message by a fresh key that isn't a member; and a
  real signature over a different message (the PR's single-key input signature), which recovers to a key
  that isn't a member.
Each trial draws 2-6 partial files, each holding 1-4 pool entries (repeats allowed), and merges them in two
independent random orders, folding one way or the other. A rule passes the trial if both merges give the same
final witness lock (or both say "not final").

The rules:
- REFERENCE (the candidate rule): verify each signature against the message; keep only members; normalize
  to low-s; key by signer; if a signer appears twice, keep the smaller normalized bytes. Finalize when the
  first R members and at least M members are present: take the first R, then the lowest member indices up to
  M, in member order.
- FIRST-SEEN (BIP-174's Combiner may "pick arbitrarily when conflicts occur"; here: keep the first bytes seen
  per signer, verified, no normalization; finalize as REFERENCE).
- STRICT (PCZT: fail when the same key has two different values; verified first, no normalization).
- CCC-LIKE (aggregateTransactions: walk the files in order, keep verified members until M, in insertion order).
Also tests R > 0 with five fresh keys (R = 2, M = 3): REFERENCE must include members 0 and 1, and must refuse
to finalize without them. Test keys are generated at run time and never stored.
"""
import hashlib
import json
import os
import pathlib
import random
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "X1" / "scripts"))
import ckbcore as c  # noqa: E402

TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
rng = random.Random(20261118)
d = json.loads((HERE / "results" / "partials.json").read_text())
MSG = c.h2b(d["message"])
MEMBERS = [c.h2b(k) for k in d["members"]]
M, R = d["threshold"], d["require_first_n"]
REAL = {int(k): c.h2b(v["signature"]) for k, v in d["signatures_by_member"].items()}


def malleate(sig):
    r, s, v = sig[:32], int.from_bytes(sig[32:64], "big"), sig[64]
    return r + (c.N - s).to_bytes(32, "big") + bytes([v ^ 1])


def low_s(sig):
    return malleate(sig) if int.from_bytes(sig[32:64], "big") > c.N // 2 else sig


_cache = {}


def signer(sig, msg, members):
    key = (sig, msg, tuple(members))
    if key not in _cache:
        _cache[key] = _signer(sig, msg, members)
    return _cache[key]


def _signer(sig, msg, members):
    try:
        kh = c.blake160(c.recover(msg, sig))
    except ValueError:
        return None
    return members.index(kh) if kh in members else None


def finalize(chosen, members, m, r):
    """chosen: {member index: signature}. Returns the lock bytes or None (not final)."""
    if any(i not in chosen for i in range(r)) or len(chosen) < m:
        return None
    pick = list(range(r)) + [i for i in sorted(chosen) if i >= r][: m - r]
    return c.multisig_script(r, m, members) + b"".join(chosen[i] for i in sorted(pick))


def rule_reference(files, msg, members, m, r):
    got = {}
    for f in files:
        for sig in f:
            i = signer(sig, msg, members)
            if i is None:
                continue
            n = low_s(sig)
            got[i] = min(got.get(i, n), n)
    return finalize(got, members, m, r)


def rule_first_seen(files, msg, members, m, r):
    got = {}
    for f in files:
        for sig in f:
            i = signer(sig, msg, members)
            if i is not None and i not in got:
                got[i] = sig
    return finalize(got, members, m, r)


def rule_strict(files, msg, members, m, r):
    got = {}
    for f in files:
        for sig in f:
            i = signer(sig, msg, members)
            if i is None:
                continue
            if i in got and got[i] != sig:
                return "FAIL: conflicting values"
            got[i] = sig
    return finalize(got, members, m, r)


def rule_ccc_like(files, msg, members, m, r):
    got = []
    seen = set()
    for f in files:
        for sig in f:
            i = signer(sig, msg, members)
            if i is None or i in seen:
                continue
            seen.add(i)
            got.append(sig)
            if len(got) >= m:
                return c.multisig_script(r, m, members) + b"".join(got)
    return None


RULES = {"reference": rule_reference, "first_seen": rule_first_seen, "strict": rule_strict, "ccc_like": rule_ccc_like}


def lock_ok(lock, msg, members, m, r):
    n = len(members)
    if lock is None or isinstance(lock, str) or len(lock) != 4 + 20 * n + 65 * m:
        return False
    used = []
    for k in range(m):
        i = signer(lock[4 + 20 * n + 65 * k: 4 + 20 * n + 65 * (k + 1)], msg, members)
        if i is None or i in used:
            return False
        used.append(i)
    return all(i in used for i in range(r))


# junk
fresh = os.urandom(32)  # a fresh non-member key, made at run time and never stored
nonmember = c.sign(MSG, fresh)
wrong_msg = c.h2b(d["single_key_signature"])
junk = [os.urandom(65), nonmember, wrong_msg]
assert signer(nonmember, MSG, MEMBERS) is None and signer(wrong_msg, MSG, MEMBERS) is None
twins = {i: malleate(s) for i, s in REAL.items()}
assert all(signer(twins[i], MSG, MEMBERS) == i and twins[i] != REAL[i] for i in REAL)
pool = list(REAL.values()) + list(twins.values()) + junk


def draw_files(pool_):
    return [[rng.choice(pool_) for _ in range(rng.randint(1, 4))] for _ in range(rng.randint(2, 6))]


def merged(rule, files, msg, members, m, r):
    order = files[:]
    rng.shuffle(order)
    if rng.random() < 0.5:  # fold from the other end, as a different merge tree would
        order = [list(reversed(f)) for f in reversed(order)]
    return rule(order, msg, members, m, r)


report = {"trials": TRIALS, "pool": {"real_signatures": 5, "malleated_twins": 5, "junk": 3}, "rules": {}}
for name, rule in RULES.items():
    same = final_same = strict_fail = invalid = 0
    for _ in range(TRIALS):
        files = draw_files(pool)
        a, b = merged(rule, files, MSG, MEMBERS, M, R), merged(rule, files, MSG, MEMBERS, M, R)
        same += a == b
        if isinstance(a, str) or isinstance(b, str):
            strict_fail += 1
        for x in (a, b):
            if x is not None and not isinstance(x, str) and not lock_ok(x, MSG, MEMBERS, M, R):
                invalid += 1
    report["rules"][name] = {"same_result_both_orders": same, "different_results": TRIALS - same,
                             "trials_where_a_merge_failed": strict_fail, "invalid_final_locks": invalid}

# the same trials with no malleated twins and no junk (only the five real signatures)
clean = {}
for name, rule in RULES.items():
    same = 0
    for _ in range(TRIALS):
        files = draw_files(list(REAL.values()))
        same += merged(rule, files, MSG, MEMBERS, M, R) == merged(rule, files, MSG, MEMBERS, M, R)
    clean[name] = {"same_result_both_orders": same, "different_results": TRIALS - same}
report["rules_with_only_real_signatures"] = clean

# idempotence of the reference rule: merging a file with itself, or a merged result with an input again
idem = 0
for _ in range(TRIALS):
    files = draw_files(pool)
    idem += rule_reference(files, MSG, MEMBERS, M, R) == rule_reference(files + files, MSG, MEMBERS, M, R)
report["reference_idempotent_trials"] = idem

# R > 0 with fresh test keys
secrets = [os.urandom(32) for _ in range(5)]  # fresh test keys, made at run time and never stored
keys5 = [c.blake160(c.pubkey_from_secret(s)) for s in secrets]
msg2 = hashlib.blake2b(b"x3a synthetic message", digest_size=32).digest()
sig2 = {i: c.sign(msg2, s) for i, s in enumerate(secrets)}
with_r = rule_reference([[sig2[4], sig2[1]], [sig2[0], sig2[3]], [sig2[2]]], msg2, keys5, 3, 2)
without_first = rule_reference([[sig2[1], sig2[2]], [sig2[3], sig2[4]]], msg2, keys5, 3, 2)
report["require_first_n_test"] = {
    "config": "R=2, M=3, N=5 (fresh test keys)",
    "all_five_signed: final": with_r is not None,
    "all_five_signed: lock valid under the lock rule": lock_ok(with_r, msg2, keys5, 3, 2),
    "all_five_signed: chosen members": [signer(with_r[4 + 100 + 65 * k: 4 + 100 + 65 * (k + 1)], msg2, keys5) for k in range(3)],
    "member_0_missing (four others signed): final": without_first is not None,
}
json.dump(report, sys.stdout, indent=1)
