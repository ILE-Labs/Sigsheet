#!/usr/bin/env python3
"""XRT-2: prototype-level checks of attacks and objections considered for the design (no chain needed).

Each check runs the design-stage prototype as it is (`../prototypes`, unchanged) and, where the objection asks for
a new rule, a candidate rule written here (throwaway, for the design decisions in design-record.md):

  unused_entries         a context entry or config that no input uses, inside a merge input: the prototype's
                         reader refuses the file before any merge; a merge of unvalidated models would carry it
                         into the result
  junk_signatures        thousands of junk signature entries: reading time, as the prototype does it (recover,
                         then check the member), and with the candidate rule (check that the filed signer is a
                         member first)
  canonical_check_first  a canonical file with a non-member signature: read without refusal (the canonical check
                         is on the parsed file, before signatures are dropped)
  template_extra_field   a witness template written as a WitnessArgs with a fourth field: what the prototype does
  duplicate_out_point    a transaction that lists one out point twice: what the prototype does

Inputs: the C files of cases R2, S3 and R1 in ../X6/interop/a-check/ (written by its make_a_check.py). R1 and R2 are mainnet cases;
see experiments/mainnet-inputs.md.

Run from experiments/XRT/:  python3 -I -X utf8 scripts/prototype_checks.py > results/prototype-checks.json
"""
import copy
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
EXP = HERE.parent
sys.path.insert(0, str(EXP / "prototypes"))
import core  # noqa: E402
import fmt_c  # noqa: E402
from core import c, SigsheetError  # noqa: E402

A_CHECK = EXP / "X6" / "interop" / "a-check"
R2 = A_CHECK / "R2-dao-payout.c.json"
S3 = A_CHECK / "S3-v2-2of3-two-inputs.c.json"


def refused(f):
    try:
        f()
        return "accepted"
    except (SigsheetError, ValueError, KeyError) as e:
        return f"refused: {e}"


def doc_of(path):
    return json.loads(path.read_text())


def enc(doc):
    return core.canon(doc).encode()


def check_unused_entries():
    doc = doc_of(R2)
    good = fmt_c.decode(enc(doc))
    # a real, hash-correct previous transaction that no input spends: R1's
    r1 = doc_of(A_CHECK / "R1-fiber-scripts-pr34.c.json")
    extra_h, extra_tx = next(iter(r1["context"].items()))
    bad = copy.deepcopy(doc)
    bad["context"][extra_h] = extra_tx
    bad_cfg = copy.deepcopy(doc)
    other = {"public_key_hashes": ["0x" + "11" * 20, "0x" + "22" * 20], "require_first_n": 0, "threshold": 1}
    cfg_id = core.config_id({"r": 0, "m": 1, "keys": other["public_key_hashes"]})
    bad_cfg["multisig_configs"][cfg_id] = other
    out = {"reader_on_file_with_unused_context": refused(lambda: fmt_c.decode(enc(bad))),
           "reader_on_file_with_unused_config": refused(lambda: fmt_c.decode(enc(bad_cfg)))}
    # an unvalidated merge (the objection considered): decode without checks, merge, re-read the result
    raw_bad = fmt_c.decode(enc(bad), check=False)
    merged = core.merge(good, raw_bad)
    out["unvalidated_merge_then_reader"] = refused(lambda: fmt_c.decode(fmt_c.encode(merged)))
    # the candidate rule: merge takes validated files only, and keeps only entries the transaction uses
    used = {i["previous_output"]["tx_hash"] for i in good.tx["inputs"]}
    merged.prevs = {h: p for h, p in merged.prevs.items() if h in used}
    needed = {c.b2h(c.h2b(g["lock"]["args"])[:20]) for g in core.lock_groups(merged).values() if g["kind"] == "multisig"}
    merged.configs = {k: v for k, v in merged.configs.items() if k in needed}
    out["candidate_rule_merge_then_reader"] = refused(lambda: fmt_c.decode(fmt_c.encode(merged)))
    return out


def check_junk_signatures():
    doc = doc_of(R2)
    gh = next(iter(doc["signatures"]))
    junk = copy.deepcopy(doc)
    import random
    rng = random.Random(9)
    for i in range(20000):  # r and s below the group order, so each entry costs a full key recovery
        r, s = rng.randrange(1, c.N), rng.randrange(1, c.N // 2)
        junk["signatures"][gh][f"0x{i:040x}"] = c.b2h(r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([rng.randrange(2)]))
    data = enc(junk)
    t0 = time.perf_counter()
    m = fmt_c.decode(data, check=False)
    ver, dropped = core.verified_sigs(m)
    t_proto = time.perf_counter() - t0
    # candidate rule: an entry filed under a key that isn't a member is dropped before any key recovery
    t0 = time.perf_counter()
    groups = core.lock_groups(m)
    g = groups[gh]
    members = set(core.group_config(m, g)["keys"])
    kept = {k: v for k, v in m.sigs[gh].items() if k in members}
    msg = core.group_message(m, g)
    valid = [k for k, v in kept.items() if core.signer_of(m, g, c.h2b(v), msg) == k]
    t_rule = time.perf_counter() - t0
    return {"junk_entries": 20000, "file_bytes": len(data), "prototype_seconds": round(t_proto, 2),
            "prototype_dropped": len(dropped), "prototype_verified": sum(len(v) for v in ver.values()),
            "candidate_rule_seconds": round(t_rule, 3), "candidate_rule_recoveries": len(kept), "candidate_rule_verified": len(valid)}


def check_canonical_first():
    doc = doc_of(R2)
    gh = next(iter(doc["signatures"]))
    bad = copy.deepcopy(doc)
    # a valid signature by a key that isn't a member (a fresh key signs the group's message)
    m = fmt_c.decode(enc(doc))
    g = core.lock_groups(m)[gh]
    msg = core.group_message(m, g)
    secret = (12345).to_bytes(32, "big")
    sig = c.sign(msg, secret)
    kh = c.b2h(c.blake160(c.pubkey_from_secret(secret)))
    bad["signatures"][gh][kh] = c.b2h(sig)
    data = enc(bad)
    try:
        warnings = core.validate(fmt_c.decode(data, check=False))
        decoded = fmt_c.decode(data)
        status = "accepted (canonical check passed on the parsed file)"
    except SigsheetError as e:
        status, warnings = f"refused: {e}", []
    return {"file_with_non_member_signature": status, "warnings": warnings[:2]}


def check_template_extra_field():
    doc = doc_of(S3)
    m = fmt_c.decode(enc(doc))
    # rewrite the first witness template as a WitnessArgs with a 4th (unknown) field: total|4 offsets|...
    four = c.dynvec([b"", c.mol_bytes(b"\x07"), b"", c.mol_bytes(b"\x01\x02")])  # lock absent, input_type set, a 4th field
    bad = copy.deepcopy(doc)
    bad["transaction"]["witnesses"][0] = c.b2h(four)
    data = enc(bad)
    status = refused(lambda: fmt_c.decode(data))
    msg_same = None
    if status == "accepted":
        m2 = fmt_c.decode(data)
        g = next(iter(core.lock_groups(m2).values()))
        three = copy.deepcopy(doc)
        three["transaction"]["witnesses"][0] = c.b2h(c.witness_args(None, b"\x07", None))
        m3 = fmt_c.decode(enc(three))
        msg_same = core.group_message(m2, g) == core.group_message(m3, next(iter(core.lock_groups(m3).values())))
    return {"template_with_a_fourth_field": status,
            "message_equals_that_of_the_same_template_without_the_4th_field": msg_same,
            "note": "the prototype parses the first three fields and rebuilds a canonical WitnessArgs for the message"}


def check_duplicate_out_point():
    doc = doc_of(S3)
    bad = copy.deepcopy(doc)
    bad["transaction"]["inputs"].append(copy.deepcopy(bad["transaction"]["inputs"][0]))
    bad["transaction"]["witnesses"].append("0x")
    data = enc(bad)
    status = refused(lambda: fmt_c.decode(data))
    fee = None
    if status == "accepted":
        m = fmt_c.decode(data)
        ins = sum(int(core.spent_output(m, i)[0]["capacity"], 16) for i in range(len(m.tx["inputs"])))
        outs = sum(int(o["capacity"], 16) for o in m.tx["outputs"])
        fee = ins - outs
    return {"transaction_listing_one_out_point_twice": status, "fee_shown_by_inputs_minus_outputs_shannons": fee}


def main():
    out = {}
    for name, f in (("unused_entries", check_unused_entries), ("junk_signatures", check_junk_signatures),
                    ("canonical_check_first", check_canonical_first),
                    ("template_extra_field", check_template_extra_field),
                    ("duplicate_out_point", check_duplicate_out_point)):
        try:
            out[name] = f()
        except Exception as e:  # noqa: BLE001
            out[name] = {"error": f"{type(e).__name__}: {e}"}
        print(name, json.dumps(out[name])[:300], file=sys.stderr)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
