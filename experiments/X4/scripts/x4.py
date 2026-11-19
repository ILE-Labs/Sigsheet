#!/usr/bin/env python3
"""X4 part 2: build a malicious file for each attack in Q6 (and the further attacks considered), in each format,
and record which check catches it.

Usage, from experiments/X4:  python3 -I -X utf8 scripts/x4.py > results/x4.json
Base cases: X2's real genesis 2-of-3 payment (R2, two real signatures) and PR #34 (R1). The checks are the
prototypes' readers: strict decoding (schema, canonical form, every profile rule), core.validate (previous
transactions by hash, configs by hash, templates), merge (same unsigned transaction; verified member signatures,
low-s, keyed by signer) and finalize (first R, M members). "Caught" means the reader refuses the file, or drops
the bad entry and the result is still correct; "not caught" means the bad data would reach the signer or the chain.
"""
import copy
import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import core  # noqa: E402
import fmt_a  # noqa: E402
import fmt_b  # noqa: E402
import fmt_c  # noqa: E402
import mol  # noqa: E402
from core import c, SigsheetError  # noqa: E402

NET = "0x92b197aa1fba0f63633922c61c92375c9c074a93e85963554f5499fe1450d0e5"


def load(name):
    d = json.loads((HERE.parent / "X2" / "cases" / name).read_text())
    m = d["model"]
    return core.Model(m["tx"], m["prevs"], m["configs"], m["sigs"])


R2 = load("R2-dao-payout.json")
R1 = load("R1-fiber-scripts-pr34.json")
FMT = {
    "C": (fmt_c.encode, fmt_c.decode),
    "B+w": (lambda m: fmt_b.encode(m, NET, True), lambda b: fmt_b.decode(b)[0]),
    "A": (fmt_a.encode, fmt_a.decode),
}


def reader(fmt, data):
    """What an honest Sigsheet reader does with a received file: decode strictly and validate; then the signer's
    view (status) and a finalize attempt. Returns (outcome, detail)."""
    enc, dec = FMT[fmt]
    try:
        m = dec(data)
    except (SigsheetError, mol.MolError, ValueError, KeyError) as e:
        return "refused", f"{type(e).__name__}: {e}"
    warnings = core.validate(m)
    ver, dropped = core.verified_sigs(m)
    st = core.status(m)
    out = {"warnings": warnings, "dropped": len(dropped), "ready": all(s["ready"] for s in st.values())}
    if out["ready"]:
        final = core.finalize(m)
        out["final_passes_lock_rules"] = all(core.lock_rule_check(final, m.prevs).values())
        out["final_tx_hash"] = c.b2h(c.tx_hash(final))
    return "accepted", out


def fee_of(m):
    ins = sum(int(core.spent_output(m, i)[0]["capacity"], 16) for i in range(len(m.tx["inputs"])))
    outs = sum(int(o["capacity"], 16) for o in m.tx["outputs"])
    return ins - outs


def run(name, build, fmts=("C", "B+w", "A")):
    res = {}
    for fmt in fmts:
        try:
            data = build(fmt)
        except (SigsheetError, ValueError) as e:
            res[fmt] = {"outcome": "cannot be written in this format", "detail": str(e)}
            continue
        outcome, detail = reader(fmt, data)
        res[fmt] = {"outcome": outcome, "detail": detail}
    return {"attack": name, "results": res}


# ------------------------------------------------------------------ helpers to tamper with encoded files

def enc(fmt, m):
    return FMT[fmt][0](m)


def tamper_json(data, fn):
    doc = json.loads(data)
    fn(doc)
    import core as _c
    return _c.canon(doc).encode()


def falsified_input(fmt):
    """The fee attack: the creator raises the spent cell's capacity in the carried previous transaction, so the
    signer would compute a small fee while the real input pays a large one."""
    m = R2.copy()
    h = m.tx["inputs"][0]["previous_output"]["tx_hash"]
    idx = int(m.tx["inputs"][0]["previous_output"]["index"], 16)
    if fmt == "C":
        def f(doc):
            o = doc["context"][h]["outputs"][idx]
            o["capacity"] = hex(int(o["capacity"], 16) + 1_000_000 * 10**8)
        return tamper_json(enc("C", m), f)
    if fmt == "B+w":
        def f(doc):
            p = mol.transaction(c.h2b(doc["inputs"][0]["SIGSHEET_IN_PREVIOUS_TX"]))
            p["outputs"][idx]["capacity"] = hex(int(p["outputs"][idx]["capacity"], 16) + 1_000_000 * 10**8)
            doc["inputs"][0]["SIGSHEET_IN_PREVIOUS_TX"] = c.b2h(mol.enc_transaction(p))
        return tamper_json(enc("B+w", m), f)
    # A: rebuild the packet with the tampered previous transaction (its hash no longer matches)
    m2 = m.copy()
    m2.prevs[h]["outputs"][idx]["capacity"] = hex(int(m2.prevs[h]["outputs"][idx]["capacity"], 16) + 10**14)
    try:
        return fmt_a.encode(m2)
    except SigsheetError:
        # the encoder itself resolves inputs through the hash check; write the bytes by hand instead
        saved = core.spent_output
        core.spent_output = lambda model, i: (model.prevs[h]["outputs"][idx], "0x")
        try:
            return fmt_a.encode(m2)
        finally:
            core.spent_output = saved


def a_resolved_inputs_only(fmt):
    """Path A only: leave input_transactions intact but raise the capacity in resolved_inputs, the field a CoBuild
    wallet that doesn't know the profile reads to show the fee."""
    data = fmt_a.encode(R2)
    v = fmt_a.to_json_view(data)["BuildingPacketV1"]
    true_cap = int(v["resolved_inputs"]["outputs"][0]["capacity"], 16)
    # rebuild with a different resolved output: patch the bytes of the first resolved output's capacity
    packet = data[4:]
    _, _, resolved, _, _, _ = mol.table(packet, 6)
    off = data.index(resolved)
    outs, _ = mol.table(resolved, 2)
    first = mol.dynvec(outs)[0]
    cap_off = off + resolved.index(first) + 16  # CellOutput table: 4-byte size + 3 offsets, then capacity
    new = bytearray(data)
    new[cap_off:cap_off + 8] = (true_cap + 10**14).to_bytes(8, "little")
    return bytes(new)


def swapped_tx(fmt):
    """The creator (or anyone passing the file on) sends signers a different transaction: an output now pays an
    attacker; the signatures already in the file were made over the original."""
    m = R2.copy()
    m.tx["outputs"][0]["lock"] = {"code_hash": core.SIGHASH[0], "hash_type": "type", "args": "0x" + "ee" * 20}
    return enc(fmt, m)


def non_member(fmt):
    m = R2.copy()
    gh = list(m.sigs)[0]
    g = core.lock_groups(m)[gh]
    stranger = os.urandom(32)
    sig = c.sign(core.group_message(m, g), stranger)
    kh = c.b2h(c.blake160(c.pubkey_from_secret(stranger)))
    m.sigs = {gh: {kh: c.b2h(sig)}}
    return enc(fmt, m)


def junk(fmt):
    """Junk entries mixed with the two real signatures: random bytes, a high-s twin, a valid signature filed under
    the wrong member, a signature over another transaction."""
    m = R2.copy()
    gh = list(m.sigs)[0]
    cfg = core.group_config(m, core.lock_groups(m)[gh])
    real = dict(m.sigs[gh])
    (k0, s0), (k1, s1) = sorted(real.items())
    third = [k for k in cfg["keys"] if k not in real][0]
    m.sigs[gh] = {k0: c.b2h(core.malleate(c.h2b(s0))), k1: s1, third: s1}
    return enc(fmt, m) if fmt != "C" else tamper_json(enc("C", m), lambda d: d["signatures"][gh].update(
        {"0x" + "11" * 20: "0x" + os.urandom(65).hex()}))


def swapped_config(fmt):
    """The multisig config is replaced by one with the attacker's keys (the signer would check membership against
    the wrong list)."""
    m = R2.copy()
    cid = next(iter(m.configs))
    bad = dict(m.configs[cid])
    bad["keys"] = ["0x" + "ee" * 20] + bad["keys"][1:]
    if fmt == "C":
        return tamper_json(enc("C", m), lambda d: d["multisig_configs"][cid].update({"public_key_hashes": bad["keys"]}))
    m.configs = {cid: bad}
    saved = core.config_id
    core.config_id = lambda cfg: cid   # let the encoder write it; the reader recomputes the hash
    try:
        return enc(fmt, m)
    finally:
        core.config_id = saved


def changed_witness(fmt):
    """After two members signed, someone changes a witness the message covers (adds a witness beyond the inputs)."""
    m = R2.copy()
    m.tx["witnesses"] = m.tx["witnesses"] + ["0xdeadbeef"]
    return enc(fmt, m)


def display_field(fmt):
    """An unauthenticated description or status for social engineering; in A, a CoBuild message
    action or a change_output the signer might trust."""
    if fmt == "C":
        return tamper_json(enc("C", R2), lambda d: d.update({"description": "routine payout, safe to sign"}))
    if fmt == "B+w":
        return tamper_json(enc("B+w", R2), lambda d: d["global"].update(
            {"SIGSHEET_GLOBAL_PROPRIETARY": {"ui:description": "0x726f7574696e65"}}))
    data = bytearray(fmt_a.encode(R2))
    # put a change_output (Some(0)) into the packet: rebuild the table with field 3 = u32(0)
    message, payload, resolved, change, infos, actions = mol.table(bytes(data[4:]), 6)
    return c.u32(0) + c.table([message, payload, resolved, c.u32(0), infos, actions])


def network_id(fmt):
    """B's network id is not signed: changing it changes nothing a signature covers."""
    data = enc("B+w", R2)
    return tamper_json(data, lambda d: d["global"].update({"SIGSHEET_GLOBAL_NETWORK_ID": "0x" + "00" * 32}))


def main():
    out = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "base_case": "R2-dao-payout (2-of-3 genesis, "
           "two real signatures)", "honest": {}, "attacks": []}
    for fmt in FMT:
        out["honest"][fmt] = reader(fmt, enc(fmt, R2))
    out["honest_fee_shannons"] = fee_of(R2)
    out["attacks"].append(run("1 falsified input cell (BIP-174's fee attack)", falsified_input))
    out["attacks"].append(run("1b A only: resolved_inputs raised, input_transactions intact", a_resolved_inputs_only,
                              ("A",)))
    # what a CoBuild reader that doesn't know the profile would compute from resolved_inputs
    v = fmt_a.to_json_view(a_resolved_inputs_only("A"))["BuildingPacketV1"]
    shown = sum(int(o["capacity"], 16) for o in v["resolved_inputs"]["outputs"]) - sum(
        int(o["capacity"], 16) for o in v["payload"]["outputs"])
    out["attacks"][-1]["profile_unaware_reader_fee_shannons"] = shown
    out["attacks"].append(run("2-3 swapped transaction / altered outputs (signatures from the original)", swapped_tx))
    out["attacks"].append(run("4 signature from a non-member", non_member))
    out["attacks"].append(run("5 junk: random bytes, a high-s twin, a signature under the wrong member", junk))
    out["attacks"].append(run("7 swapped multisig config", swapped_config))
    out["attacks"].append(run("10 a covered witness changed after signing", changed_witness))
    out["attacks"].append(run("9 display field (description, CoBuild message or change_output)", display_field))
    out["attacks"].append(run("6c B's network id changed", network_id, ("B+w",)))
    # merge-level checks
    honest = fmt_c.decode(fmt_c.encode(R2))
    try:
        core.merge(honest, fmt_c.decode(swapped_tx("C"), check=False))
        merge_swapped = "merged (wrong)"
    except SigsheetError as e:
        merge_swapped = f"refused: {e}"
    out["merge_honest_with_swapped_tx"] = merge_swapped
    bad = fmt_c.decode(junk("C"), check=False)
    merged = core.merge(honest, bad)
    out["merge_honest_with_junk"] = {"signers_kept": sorted(merged.sigs[list(merged.sigs)[0]]),
                                     "equals_honest": merged == honest}
    # replay: the same final transaction a second time (its inputs are spent); a signature reused on another tx
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
