#!/usr/bin/env python3
"""XRT-3: lock groups a reader doesn't sign, on the devnet.

A v2 2-of-3 multisig input next to an input under a lock the reader doesn't sign. To have such a lock on this
devnet, the "v1 reader" here is the prototype with the single-key lock treated as unknown (core.lock_kind
patched); a "v0.2 reader" is the prototype as it is (it signs the single-key lock). Fresh test keys
(keys/xrt/keys.json): multisig members x0, x1, x2; the other lock's key x3.

  A. Partial finalize (the candidate rule): the v1 reader signs and finalizes only the groups it knows,
     leaving the other group's witness as in the template; then the other lock's own signer adds its witness
     to the final transaction; sent. Shows the multisig signatures survive it (the multisig message doesn't
     cover another group's witness, background.md section 1).
  B. Carrying another group's signature: the v0.2 reader signs the other group into the file; the v1
     reader then merges its own signatures. Today's v1 rule drops the other group's signature; the candidate
     rule keeps it unchanged (unverified), and the v0.2 reader finalizes everything; sent.
  C. Since: a genesis 2-of-3 with 20-byte args, spent with a since flag set on the
     input: checked with test_tx_pool_accept (genesis and 2024 call check_since(0), background.md section 3).

Run from experiments/XRT/ with the devnet running:
    python3 -I -X utf8 scripts/unknown_groups.py > results/unknown-groups.json
"""
import copy
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
CAP = 200 * devnet.CKB
REAL_LOCK_KIND = core.lock_kind


def v1_reader(on):
    """Patch the prototype so the single-key lock is a kind it doesn't sign (on) or restore it (off)."""
    core.lock_kind = (lambda lock: "unknown" if REAL_LOCK_KIND(lock) == "sighash" else REAL_LOCK_KIND(lock)) if on else REAL_LOCK_KIND


def merge_keeping_unknown(*models):
    """Candidate rule: like core.merge, but entries filed under a group of a kind this reader doesn't sign are
    kept unchanged and unverified (the smaller bytes on a conflict), so a later reader can use them."""
    out = core.merge(*models)
    groups = core.lock_groups(out)
    for m in models:
        for gh, entries in m.sigs.items():
            g = groups.get(gh)
            if g is not None and g["kind"] == "unknown":
                for kh, sig in entries.items():
                    cur = out.sigs.setdefault(gh, {}).get(kh)
                    if cur is None or c.h2b(sig) < c.h2b(cur):
                        out.sigs[gh][kh] = sig
    return out


def finalize_partial(model):
    """Candidate rule: finalize the groups this reader signs; leave every other group's witness as in the template."""
    return core.finalize(model, require_all=False)


def build(cells, outputs_to):
    """An unsigned model spending the given (tx_hash, index) cells, all from one funding transaction."""
    fund_hash = cells[0][0]
    prev = core.raw_of(devnet.get_tx(fund_hash))
    total = sum(int(prev["outputs"][i]["capacity"], 16) for _, i in cells)
    deps = [devnet.cell_dep("v2"), devnet.cell_dep("sighash")]
    tx = {"version": "0x0", "cell_deps": deps, "header_deps": [],
          "inputs": [{"since": "0x0", "previous_output": {"tx_hash": h, "index": hex(i)}} for h, i in cells],
          "outputs": [{"capacity": hex(total - devnet.FEE), "lock": devnet.sighash_lock(outputs_to), "type": None}],
          "outputs_data": ["0x"], "witnesses": ["0x"] * len(cells)}
    return tx, prev


def main():
    k0 = devnet.KEYS["k0"]["blake160"]
    lock_ms, cfg = devnet.multisig_lock("v2", 0, 2, [KEYS[i]["blake160"] for i in range(3)])
    other = devnet.sighash_lock(KEYS[3]["blake160"])
    g_lock, g_cfg = devnet.multisig_lock("genesis", 0, 2, [KEYS[i]["blake160"] for i in range(3)])
    outs = [{"capacity": hex(CAP), "lock": lock_ms, "type": None}, {"capacity": hex(CAP), "lock": other, "type": None},
            {"capacity": hex(CAP), "lock": lock_ms, "type": None}, {"capacity": hex(CAP), "lock": other, "type": None},
            {"capacity": hex(CAP), "lock": g_lock, "type": None}]
    fund_hash, _ = devnet.fund(outs)
    report = {"funding_tx": fund_hash}
    cid = core.config_id(cfg)
    ms_gh = c.b2h(c.script_hash(lock_ms))
    other_gh = c.b2h(c.script_hash(other))

    # ---- A. partial finalize, then the other lock's own signer
    tx, prev = build([(fund_hash, 0), (fund_hash, 1)], k0)
    v1_reader(True)
    m = core.Model(tx, {fund_hash: prev}, {cid: cfg}, {})
    for i in (0, 1):
        core.sign_group(m, ms_gh, KEYS[i]["secret"])
    st = core.status(m)
    try:
        core.finalize(m)
        a_full = "finalized"
    except core.SigsheetError as e:
        a_full = f"refused: {e}"
    partial = finalize_partial(m)
    v1_reader(False)
    final = copy.deepcopy(partial)
    devnet.sign_sighash_inputs(final, KEYS[3]["secret"], [1])  # the other lock's own signer, after finalize
    dry = devnet.try_rpc("test_tx_pool_accept", [final, "passthrough"])
    sent = None
    if dry["ok"]:
        sent = devnet.rpc("send_transaction", [final, "passthrough"])
        devnet.wait_committed(sent)
    report["A_partial_finalize"] = {"v1_status": {k[:12]: v for k, v in st.items()}, "v1_full_finalize": a_full,
                                    "multisig_witness_written": partial["witnesses"][0] != "0x",
                                    "other_group_witness_left_as_template": partial["witnesses"][1] == "0x",
                                    "after_other_signer": {"dry_run_ok": dry["ok"], "error": dry.get("error"), "tx": sent}}

    # ---- B. carrying the other group's signature through a v1 reader
    tx, prev = build([(fund_hash, 2), (fund_hash, 3)], k0)
    base = core.Model(tx, {fund_hash: prev}, {cid: cfg}, {})
    v02 = base.copy()
    core.sign_group(v02, other_gh, KEYS[3]["secret"])  # v0.2 knows the single-key lock
    v1_reader(True)
    mine = base.copy()
    core.sign_group(mine, ms_gh, KEYS[0]["secret"])
    core.sign_group(mine, ms_gh, KEYS[1]["secret"])
    today = core.merge(mine, v02)  # today's v1 rule
    kept = merge_keeping_unknown(mine, v02)  # candidate rule
    v1_reader(False)
    report["B_carry"] = {"todays_v1_merge_keeps_other_group_signature": other_gh in today.sigs and bool(today.sigs[other_gh]),
                         "candidate_rule_keeps_it": other_gh in kept.sigs and bool(kept.sigs[other_gh])}
    final_b = core.finalize(kept)  # the v0.2 reader finalizes both groups
    dry = devnet.try_rpc("test_tx_pool_accept", [final_b, "passthrough"])
    sent_b = None
    if dry["ok"]:
        sent_b = devnet.rpc("send_transaction", [final_b, "passthrough"])
        devnet.wait_committed(sent_b)
    report["B_carry"]["v02_finalize_after_candidate_merge"] = {"dry_run_ok": dry["ok"], "error": dry.get("error"), "tx": sent_b}

    # ---- C. since flags on a genesis 20-byte-args input
    tx = {"version": "0x0", "cell_deps": [devnet.cell_dep("genesis")], "header_deps": [],
          "inputs": [{"since": hex((1 << 63) | 1), "previous_output": {"tx_hash": fund_hash, "index": "0x4"}}],
          "outputs": [{"capacity": hex(CAP - devnet.FEE), "lock": devnet.sighash_lock(k0), "type": None}],
          "outputs_data": ["0x"], "witnesses": ["0x"]}
    m = core.Model(tx, {fund_hash: core.raw_of(devnet.get_tx(fund_hash))}, {core.config_id(g_cfg): g_cfg}, {})
    g_gh = c.b2h(c.script_hash(g_lock))
    for i in (0, 1):
        core.sign_group(m, g_gh, KEYS[i]["secret"])
    warnings = core.validate(m)
    ftx = core.finalize(m)
    dry = devnet.try_rpc("test_tx_pool_accept", [ftx, "passthrough"])
    tx0 = copy.deepcopy(tx)
    tx0["inputs"][0]["since"] = "0x0"
    m0 = core.Model(tx0, m.prevs, m.configs, {})
    for i in (0, 1):
        core.sign_group(m0, g_gh, KEYS[i]["secret"])
    dry0 = devnet.try_rpc("test_tx_pool_accept", [core.finalize(m0), "passthrough"])
    report["C_since_genesis_20_byte_args"] = {"input_since": tx["inputs"][0]["since"], "prototype_warnings": warnings,
                                               "dry_run_with_since": {"ok": dry["ok"], "error": (dry.get("error") or "")[:160]},
                                               "control_since_0": {"ok": dry0["ok"], "error": dry0.get("error")}}
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
