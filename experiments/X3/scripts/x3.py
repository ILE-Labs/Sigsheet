#!/usr/bin/env python3
"""X3: is merging safe in any order, any number of times, with junk? Property tests on every format.

Usage, from experiments/X3:  python3 -I -X utf8 scripts/x3.py [trials] > results/x3.json
(Needs the devnet for the three new cases' previous transactions and their final commits.)

Cases: R1 (PR #34: five real member signatures and the single-key one), S6 (two multisig groups), S7 (multisig
and single key), and three new devnet cases from the funded cells (X5/data/funding.json):
- S10: the same multisig script [s1, s2, s3] under the genesis and v2 deployments in one transaction: two lock
  groups with the same args, so a signature map keyed by args (as ckb-cli's) would mix their signatures;
- S11: the same script under v2 with 20-byte args and with 28-byte args (a since): two groups, one config;
- R1-35: 3-of-5 [s1..s5] with R = 1 (s1 must sign).
For the devnet cases, every member signs with the prototypes' signer (fresh test keys).

Pool per group: every valid member signature, its high-s twin, a second valid low-s signature by the same member
(another nonce), and junk: 65 random bytes; a valid signature over the same message by a non-member; a member's
signature over another group's message; a member's signature over a different transaction; a valid signature
filed under the wrong member; a 64-byte truncated signature. Each trial draws 2-6 partial files (the unsigned
file plus 1-4 pool entries each, under the key they claim), encodes them in the format, then merges them in
three ways (left fold, right fold, a random tree over a shuffled order), each from the encoded files. Pass: all
three give the same bytes; merging the result with itself or with any of its inputs changes nothing; no junk
survives; and when ready, the finalized transaction passes the lock's rules in Python. A file for a different
transaction must be refused.
"""
import json
import os
import pathlib
import random
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import core  # noqa: E402
import devnet  # noqa: E402
import fmt_a  # noqa: E402
import fmt_b  # noqa: E402
import fmt_c  # noqa: E402
from core import c, SigsheetError  # noqa: E402

TRIALS = int(sys.argv[1]) if len(sys.argv) > 1 else 500
rng = random.Random(20261118)
NET = "0x" + "00" * 32
CODECS = {
    "C": (fmt_c.encode, lambda b: fmt_c.decode(b, check=False)),
    "B+w": (lambda m: fmt_b.encode(m, NET, True), lambda b: fmt_b.decode(b, check=False)[0]),
    "A": (fmt_a.encode, lambda b: fmt_a.decode(b, check=False)),
}
CKB = devnet.CKB
S6 = devnet.sighash_lock(devnet.KEYS["s6"]["blake160"])


def load_case(name):
    d = json.loads((HERE.parent / "X2" / "cases" / name).read_text())
    m = d["model"]
    return core.Model(m["tx"], m["prevs"], m["configs"], m["sigs"])


def devnet_cases():
    s10 = devnet.spend_model([("A23G", 2), ("A23V", 2)], [(S6, 1999 * CKB)])
    s11 = devnet.spend_model([("A23V", 3), ("A23VS", 0)], [(S6, 1999 * CKB)], since_for={"A23VS": 100})
    r135 = devnet.spend_model([("B35VR", 0)], [(S6, 999 * CKB)])
    out = {}
    for name, m, members in (("S10-same-script-two-deployments", s10, ["s1", "s2", "s3"]),
                             ("S11-same-script-20-and-28-byte-args", s11, ["s1", "s2", "s3"]),
                             ("R1-35-first-member-required", r135, ["s1", "s2", "s3", "s4", "s5"])):
        for gh in core.lock_groups(m):
            for k in members:
                core.sign_group(m, gh, devnet.secret(k))
        out[name] = m
    return out


def pools(model):
    """{group: [(claimed key, signature bytes, is_valid)]} built from the model's own signatures."""
    groups = core.lock_groups(model)
    stranger = os.urandom(32)
    other = model.copy()
    other.tx["outputs"][0]["capacity"] = hex(int(other.tx["outputs"][0]["capacity"], 16) - 1)
    msgs = {gh: core.group_message(model, g) for gh, g in groups.items() if g["kind"] != "unknown"}
    out = {}
    for gh, entries in model.sigs.items():
        g = groups[gh]
        members = core.group_config(model, g)["keys"] if g["kind"] == "multisig" else [g["lock"]["args"]]
        p = []
        for kh, sig in entries.items():
            s = c.h2b(sig)
            p.append((kh, s, True))
            p.append((kh, core.malleate(s), True))                       # high-s twin
        for kh in list(entries)[:2]:
            # a second valid low-s signature by the same member, if we hold its key (devnet cases)
            sec = next((k["secret"] for k in devnet.KEYS.values() if k["blake160"] == kh), None)
            if sec:
                p.append((kh, c.sign(msgs[gh], c.h2b(sec), nonce=b"another nonce"), True))
        k0 = members[0]
        p.append((k0, os.urandom(65), False))                              # random bytes
        p.append((k0, c.sign(msgs[gh], stranger), False))                  # non-member, same message
        other_gh = [x for x in msgs if x != gh]
        if other_gh:                                                         # another group's message
            sec = next((k["secret"] for k in devnet.KEYS.values() if k["blake160"] == k0), None)
            if sec:
                p.append((k0, c.sign(msgs[other_gh[0]], c.h2b(sec)), False))
        og = core.lock_groups(other)[gh]
        sec = next((k["secret"] for k in devnet.KEYS.values() if k["blake160"] == k0), None)
        if sec:
            p.append((k0, c.sign(core.group_message(other, og), c.h2b(sec)), False))   # another transaction
        first_valid = next(iter(entries.items()))
        wrong = [m for m in members if m != first_valid[0]]
        if wrong:
            p.append((wrong[0], c.h2b(first_valid[1]), False))              # filed under the wrong member
        p.append((k0, c.h2b(first_valid[1])[:64], False))                   # truncated
        out[gh] = p
    return out


def partial(base, picks):
    m = base.copy()
    m.sigs = {}
    for gh, (kh, sig, _) in picks:
        m.sigs.setdefault(gh, {})
        if kh in m.sigs[gh]:      # one entry per key per file (a map); a later pick overwrites
            pass
        m.sigs[gh][kh] = c.b2h(sig)
    return m


def merge_bytes(enc, dec, files):
    return enc(core.merge(*[dec(f) for f in files]))


def tree(enc, dec, files):
    if len(files) == 1:
        return files[0]
    cut = rng.randint(1, len(files) - 1)
    return merge_bytes(enc, dec, [tree(enc, dec, files[:cut]), tree(enc, dec, files[cut:])])


def run_case(name, full, trials):
    base = full.copy()
    base.sigs = {}
    pool = pools(full)
    flat = [(gh, e) for gh, es in pool.items() for e in es]
    res = {}
    for fmt, (enc, dec) in CODECS.items():
        ok = idem = junk_free = rules_ok = ready_n = 0
        failures = []
        usable = [x for x in flat if fmt != "A" or len(x[1][1]) == 65]   # A's fixed fields can't hold a 64-byte one
        res_unrepresentable = len(flat) - len(usable)
        for t in range(trials):
            n = rng.randint(2, 6)
            files = [enc(partial(base, [rng.choice(usable) for _ in range(rng.randint(1, 4))])) for _ in range(n)]
            a = files[0]
            for f in files[1:]:
                a = merge_bytes(enc, dec, [a, f])
            b = files[-1]
            for f in reversed(files[:-1]):
                b = merge_bytes(enc, dec, [f, b])
            sh = files[:]
            rng.shuffle(sh)
            tr = tree(enc, dec, sh)
            if a == b == tr:
                ok += 1
            elif len(failures) < 3:
                failures.append(t)
            if merge_bytes(enc, dec, [a, a]) == a and all(merge_bytes(enc, dec, [a, f]) == a for f in files):
                idem += 1
            merged = dec(a)
            # every surviving signature verifies and was in the valid pool
            valid = {(gh, kh, c.b2h(core.low_s(s))) for gh, (kh, s, v) in flat if v}
            surv = {(gh, kh, s) for gh, es in merged.sigs.items() for kh, s in es.items()}
            if surv <= valid:
                junk_free += 1
            st = core.status(merged)
            if all(x["ready"] for x in st.values()):
                ready_n += 1
                final = core.finalize(merged)
                if all(core.lock_rule_check(final, merged.prevs).values()):
                    rules_ok += 1
        res[fmt] = {"trials": trials, "same_bytes_all_three_merges": ok, "idempotent": idem, "junk_free": junk_free,
                    "ready": ready_n, "finalized_pass_lock_rules": rules_ok, "first_failures": failures,
                    "pool_entries_the_format_cannot_hold": res_unrepresentable}
    # a file for another transaction is refused
    other = base.copy()
    other.tx["outputs"][0]["capacity"] = hex(int(other.tx["outputs"][0]["capacity"], 16) - 1)
    try:
        core.merge(base, other)
        res["different_transaction_refused"] = False
    except SigsheetError:
        res["different_transaction_refused"] = True
    res["pool_size"] = len(flat)
    res["valid_in_pool"] = sum(1 for _, e in flat if e[2])
    return res


def first_r_check(m):
    """R = 1: without s1 the group can't finalize; with s1 and others it picks s1 then the lowest indices."""
    gh = list(m.sigs)[0]
    cfg = core.group_config(m, core.lock_groups(m)[gh])
    s1 = cfg["keys"][0]
    without = m.copy()
    del without.sigs[gh][s1]
    out = {"ready_without_s1": core.status(without)[gh]["ready"], "signers_without_s1": core.status(without)[gh]["signed"]}
    try:
        core.finalize(without)
        out["finalize_without_s1"] = "finalized (wrong)"
    except SigsheetError as e:
        out["finalize_without_s1"] = f"refused: {e}"
    final = core.finalize(m)
    lock, _, _ = c.parse_witness_args(c.h2b(final["witnesses"][0]))
    msg = core.group_message(m, core.lock_groups(m)[gh])
    picked = [cfg["keys"].index(c.b2h(c.blake160(c.recover(msg, lock[104 + 65 * j:104 + 65 * (j + 1)])))) for j in range(3)]
    out["picked_member_indices"] = picked
    return out, final


def main():
    out = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "trials_per_case_and_format": TRIALS,
           "cases": {}, "devnet": {}}
    cases = {"R1-fiber-scripts-pr34": load_case("R1-fiber-scripts-pr34.json"),
             "S6-two-multisig-groups": None, "S7-multisig-plus-single-key": None}
    # S6 and S7: X1's signatures plus fresh ones are not available for their keys in every group (X1 keys), so
    # they are loaded with their committed signatures only.
    cases["S6-two-multisig-groups"] = load_case("S6-two-multisig-groups.json")
    cases["S7-multisig-plus-single-key"] = load_case("S7-multisig-plus-single-key.json")
    dn = devnet_cases()
    cases.update(dn)
    for name, m in cases.items():
        # PR #34's 284 KB previous transaction makes each merge ~0.15 s in pure Python: a quarter of the trials there
        out["cases"][name] = run_case(name, m, max(20, TRIALS // 4) if name.startswith("R1-fiber") else TRIALS)
        print(name, {k: v["same_bytes_all_three_merges"] for k, v in out["cases"][name].items() if isinstance(v, dict)},
              file=sys.stderr)
    # S10: what a map keyed by lock args would do (ckb-cli's tx file keys signatures by lock args)
    s10 = dn["S10-same-script-two-deployments"]
    groups = core.lock_groups(s10)
    by_args = {}
    for gh, es in s10.sigs.items():
        by_args.setdefault(groups[gh]["lock"]["args"], []).extend(es.values())
    out["S10_keyed_by_args"] = {args: len(v) for args, v in by_args.items()}
    out["S10_keyed_by_lock_hash"] = {gh: len(v) for gh, v in s10.sigs.items()}
    out["S10_args_identical_across_groups"] = len({g["lock"]["args"] for g in groups.values()}) == 1
    # first R
    fr, final_r = first_r_check(dn["R1-35-first-member-required"])
    out["first_r"] = fr
    # commit the three new cases on the devnet, finalized from the merged C file
    for name, m in dn.items():
        final = core.finalize(m)
        dry = devnet.try_rpc("test_tx_pool_accept", [final, "passthrough"])
        e = {"dry_run": dry, "tx_hash": c.b2h(c.tx_hash(final))}
        if dry["ok"]:
            h = devnet.rpc("send_transaction", [final, "passthrough"])
            devnet.wait_committed(h)
            e["committed_block"] = int(devnet.rpc("get_transaction", [h])["tx_status"]["block_number"], 16)
        out["devnet"][name] = e
        (HERE / "cases").mkdir(exist_ok=True)
        (HERE / "cases" / f"{name}.json").write_text(json.dumps({"model": {"tx": m.tx, "prevs": m.prevs,
                                                                           "configs": m.configs, "sigs": m.sigs}},
                                                                 indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
