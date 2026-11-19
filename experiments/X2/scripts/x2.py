#!/usr/bin/env python3
"""X2: does each format round-trip every case, and what does a signer's message computation read?

Usage, from experiments/X2:  python3 -I -X utf8 scripts/x2.py > results/x2.json
(Run ../prototypes/cases.py first; it writes cases/*.json from the cases' own files.)

For every case (2 real, 10 X1 devnet cases) and every format (C; B as revised; B+w, B with the witness
templates added; A, the building-packet profile in Molecule):
 1. encode the case's model; record the size (and zlib-compressed size, level 9);
 2. decode strictly (schema, canonical form, every profile rule) and compare with the model: lossless?
 3. from the encoded file alone, compute every lock group's message through the format's own field names,
    recording every field read; compare with X1's messages for the case;
 4. verify every carried signature against those messages (recover the key, check membership);
 5. finalize when ready (the finalize rule, D12) and run the lock's rules on the result in Python; compare the
    transaction hash with the committed one.
Then the C4 test: C -> A -> C and A -> C -> A, byte for byte, with the messages and signatures checked on
both sides. And the IDL boundary test: the fields read in step 3, collapsed and classified.
"""
import json
import pathlib
import sys
import time
import zlib

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import core  # noqa: E402
import fmt_a  # noqa: E402
import fmt_b  # noqa: E402
import fmt_c  # noqa: E402
from core import c, SigsheetError  # noqa: E402
from record import summarize  # noqa: E402

FORMATS = {
    "C": (lambda m, net: fmt_c.encode(m), lambda b: fmt_c.decode(b, check=False), fmt_c.messages_from_file),
    "B": (lambda m, net: fmt_b.encode(m, net), lambda b: fmt_b.decode(b, check=False)[0], fmt_b.messages_from_file),
    "B+w": (lambda m, net: fmt_b.encode(m, net, True), lambda b: fmt_b.decode(b, check=False)[0],
            fmt_b.messages_from_file),
    "A": (lambda m, net: fmt_a.encode(m), lambda b: fmt_a.decode(b, check=False), fmt_a.messages_from_file),
}


def classify(path, fmt):
    """Which part of the file a field read belongs to (the boundary ruling's categories)."""
    p = path
    if fmt == "C":
        if p.startswith("transaction"):
            return "the transaction"
        if p.startswith("context"):
            if ".lock." in p or p.endswith(".lock"):
                return "the previous transactions: the spent output's lock (code hash, hash type, args)"
            return "the previous transactions"
        if p.startswith("multisig_configs"):
            return "the multisig config"
    if fmt in ("B", "B+w"):
        if "SIGSHEET_GLOBAL_RAW_TX" in p or "SIGSHEET_GLOBAL_WITNESSES" in p:
            return "the transaction"
        if "SIGSHEET_IN_PREVIOUS_TX" in p:
            return "the previous transactions (Molecule blob; the lock is read inside it)"
        if "SIGSHEET_IN_MULTISIG_CONFIG" in p:
            return "the multisig config"
        if p in ("global", "inputs", "inputs[#]", "inputs[]"):
            return "containers"
    if fmt == "A":
        if p.startswith("BuildingPacketV1.payload"):
            return "the transaction"
        if ".data.input_transactions" in p:
            if ".lock." in p or p.endswith(".lock"):
                return "the previous transactions: the spent output's lock (code hash, hash type, args)"
            return "the previous transactions"
        if ".data.config" in p:
            return "the multisig config"
        if p in ("BuildingPacketV1", "BuildingPacketV1.lock_actions", "BuildingPacketV1.lock_actions[#]",
                 "BuildingPacketV1.lock_actions[]", "BuildingPacketV1.lock_actions[].data"):
            return "containers"
    return "OTHER"


def load(f):
    d = json.loads(f.read_text())
    m = d["model"]
    return d, core.Model(m["tx"], m["prevs"], m["configs"], m["sigs"])


def run_case(d, model):
    net = d["network_genesis_hash"]
    exp = d["expected"]
    out = {"id": d["id"], "formats": {}}
    for name, (enc, dec, msgs_of) in FORMATS.items():
        r = {}
        t0 = time.perf_counter()
        data = enc(model, net)
        r["encode_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        r["bytes"] = len(data)
        r["bytes_zlib9"] = len(zlib.compress(data, 9))
        t0 = time.perf_counter()
        try:
            back = dec(data)
            r["decode_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            r["lossless"] = back == model
            r["canonical_reencode"] = enc(back, net) == data
        except SigsheetError as e:
            r["decode_error"] = str(e)
            r["lossless"] = False
            back = None
        log = set()
        t0 = time.perf_counter()
        msgs = msgs_of(data, log)
        r["messages_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        r["messages_match_expected"] = msgs == exp["model_messages"]
        r["x1_messages_found"] = sorted(exp["x1_messages"].values()) == sorted(
            m for m in msgs.values() if m in exp["x1_messages"].values()) and all(
            m in msgs.values() for m in exp["x1_messages"].values())
        fields = summarize(log)
        r["fields_read"] = fields
        r["field_classes"] = sorted({classify(p, name) for p in fields})
        # verify every carried signature with the file's own messages
        if back is not None:
            groups = core.lock_groups(back)
            n_ok = n_all = 0
            for gh, entries in model.sigs.items():
                g = groups.get(gh)
                for kh, sig in entries.items():
                    n_all += 1
                    if g and msgs.get(gh) and core.signer_of(back, g, c.h2b(sig), c.h2b(msgs[gh])) == kh:
                        n_ok += 1
            r["signatures_verified"] = f"{n_ok}/{n_all}"
            st = core.status(back)
            r["ready"] = all(s["ready"] for s in st.values())
            if r["ready"]:
                final = core.finalize(back)
                rules = core.lock_rule_check(final, back.prevs)
                r["finalized_lock_rules_pass"] = all(rules.values())
                r["final_tx_hash"] = c.b2h(c.tx_hash(final))
                r["final_tx_hash_matches_case"] = r["final_tx_hash"] == exp["tx_hash"]
        out["formats"][name] = r
    # the 1:1 JSON view of A, size only
    a = fmt_a.encode(model)
    view = json.dumps(fmt_a.to_json_view(a), sort_keys=True, separators=(",", ":")).encode()
    out["formats"]["A-json-view"] = {"bytes": len(view), "bytes_zlib9": len(zlib.compress(view, 9))}
    # C4: C -> A -> C and A -> C -> A, byte for byte
    cb = fmt_c.encode(model)
    ab = fmt_a.encode(fmt_c.decode(cb))
    cb2 = fmt_c.encode(fmt_a.decode(ab))
    ab2 = fmt_a.encode(fmt_c.decode(fmt_c.encode(fmt_a.decode(a))))
    la, lc = set(), set()
    out["c4_mapping"] = {
        "C_to_A_to_C_identical": cb2 == cb,
        "A_to_C_to_A_identical": ab2 == a,
        "messages_equal_on_both_sides": fmt_c.messages_from_file(cb, lc) == fmt_a.messages_from_file(ab, la),
        "signatures_equal_on_both_sides": fmt_a.decode(ab).sigs == fmt_c.decode(cb).sigs,
    }
    return out


def main():
    cases = sorted((HERE / "cases").glob("*.json"))
    results, union = [], {k: set() for k in FORMATS}
    for f in cases:
        d, model = load(f)
        r = run_case(d, model)
        for k in FORMATS:
            union[k] |= set(r["formats"][k]["fields_read"])
        results.append(r)
    boundary = {}
    for k, paths in union.items():
        classes = {}
        for p in sorted(paths):
            classes.setdefault(classify(p, k), []).append(p)
        boundary[k] = {"classes": sorted(classes), "other_fields": classes.get("OTHER", []),
                       "holds": "OTHER" not in classes, "paths": sorted(paths)}
    summary = {}
    for k in list(FORMATS) + ["A-json-view"]:
        summary[k] = {r["id"]: {x: r["formats"][k].get(x) for x in
                                ("bytes", "bytes_zlib9", "lossless", "messages_match_expected", "signatures_verified",
                                 "finalized_lock_rules_pass")} for r in results}
    print(json.dumps({"conditions": {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
                                     "python": sys.version.split()[0], "cases": [f.stem for f in cases]},
                      "summary": summary, "boundary": boundary, "cases": results}, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
