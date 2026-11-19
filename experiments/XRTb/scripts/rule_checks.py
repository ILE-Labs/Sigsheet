#!/usr/bin/env python3
"""XRTb-2: design version 2's rules against the candidate rules, offline.

The design-stage prototype (../prototypes, unchanged) supplies the reader, merge, finalize and the lock's own rules;
version 2's rules and the candidate rules are written here, as XRT did. Keys are ephemeral (made at run time,
never stored, never on a chain). One synthetic previous transaction (hashed, so the files' context checks pass)
holds five cells:
  0  a v2 2-of-3 multisig cell (members K0-K2), 1,000 CKB
  1  a single-key cell (K3), 500 CKB
  2  an Omnilock multisig-mode cell: Omnilock's code hash (CCC's mainnet table), args 0x06 | blake160(script of a
     2-of-3 of K4-K6) | 0x00 (omni_lock.c L137-L139: <identity, 21 bytes> <omni_lock args>), 300 CKB
  3  a token cell under the multisig: xUDT's code hash (CCC's mainnet table), data a 16-byte amount 1,000,000, 200 CKB
  4  a single-key cell whose args are 32 bytes, 100 CKB

  conflict_in_unsigned_group: a group the reader doesn't sign (as XRT-3: the "v1 reader" is the prototype with the single-key lock treated
       as unknown): an honest copy with K3's valid signature, an attacker's copy with 65 zero bytes under K3.
  configs_for_no_input: 50 configs that hash to their keys but belong to no input; version 2 keeps them; the candidate rule keeps a
       config only when its key occurs in some input's lock args.
  omnilock_group_carried: the Omnilock group next to the multisig group: check 7, the config rule, partial finalize.
  single_key_args_length: the single-key input with 32-byte args.
  token_display: what a signer is shown under version 2's display rules and the candidate rules: the token cell spent with
       no token output; and a single-key input's change in a mixed transaction.

Run from experiments/XRTb/:  python3 -I -X utf8 scripts/rule_checks.py > results/rule-checks.json
"""
import copy
import json
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import core  # noqa: E402
import fmt_c  # noqa: E402
from core import c  # noqa: E402

CKB = 100_000_000
V2 = ("0x36c971b8d41fbd94aabca77dc75e826729ac98447b46f91e00796155dddb0d29", "data1")
OMNILOCK = ("0x9b819793a64463aed77c615d6cb226eea5487ccfc0783043a587254cda2b6f26", "type")   # CCC, clientPublicMainnet.advanced.ts L294-L297
TOKENS = {("0x50bd8d6680b8b9cf98b73f3c08faf8b2a21914311954118ad6609be6e78a1b95", "data1"): "xUDT",  # CCC L140-L143
          ("0x5e7a36a77e68eecc013dfa2fe6a23f3b6c344b04005808694ae6dd45eea4cfd5", "type"): "sUDT"}   # CCC L123-L126
REAL_LOCK_KIND = core.lock_kind


def key():
    while True:
        s = int.from_bytes(os.urandom(32), "big")
        if 0 < s < c.N:
            break
    sec = s.to_bytes(32, "big")
    return {"secret": c.b2h(sec), "blake160": c.b2h(c.blake160(c.pubkey_from_secret(sec)))}


K = [key() for _ in range(8)]
CFG = {"r": 0, "m": 2, "keys": [K[i]["blake160"] for i in range(3)]}
CFG_OMNI = {"r": 0, "m": 2, "keys": [K[i]["blake160"] for i in (4, 5, 6)]}
MS = {"code_hash": V2[0], "hash_type": V2[1], "args": core.config_id(CFG)}
OMNI = {"code_hash": OMNILOCK[0], "hash_type": OMNILOCK[1], "args": "0x06" + core.config_id(CFG_OMNI)[2:] + "00"}
SK = {"code_hash": core.SIGHASH[0], "hash_type": core.SIGHASH[1], "args": K[3]["blake160"]}
SK32 = {"code_hash": core.SIGHASH[0], "hash_type": core.SIGHASH[1], "args": K[7]["blake160"] + "00" * 12}
TOKEN = {"code_hash": "0x50bd8d6680b8b9cf98b73f3c08faf8b2a21914311954118ad6609be6e78a1b95", "hash_type": "data1", "args": "0x" + "11" * 32}
OTHER = {"code_hash": core.SIGHASH[0], "hash_type": core.SIGHASH[1], "args": "0x" + "22" * 20}


def cell(ckb, lock, typ=None):
    return {"capacity": hex(int(ckb * CKB)), "lock": lock, "type": typ}


PREV = {"version": "0x0", "cell_deps": [], "header_deps": [],
        "inputs": [{"since": "0x0", "previous_output": {"tx_hash": "0x" + "ab" * 32, "index": "0x0"}}],
        "outputs": [cell(1000, MS), cell(500, SK), cell(300, OMNI), cell(200, MS, TOKEN), cell(100, SK32)],
        "outputs_data": ["0x", "0x", "0x", c.b2h((1_000_000).to_bytes(16, "little")), "0x"]}
PH = c.b2h(c.tx_hash(PREV))


def spend(indices, outputs, data=None, configs=None):
    tx = {"version": "0x0", "cell_deps": [], "header_deps": [],
          "inputs": [{"since": "0x0", "previous_output": {"tx_hash": PH, "index": hex(i)}} for i in indices],
          "outputs": outputs, "outputs_data": data or ["0x"] * len(outputs), "witnesses": ["0x"] * len(indices)}
    cf = {}
    for i in indices:
        lk = PREV["outputs"][i]["lock"]
        if lk is MS:
            cf[core.config_id(CFG)] = CFG
        if lk is OMNI:
            cf[core.config_id(CFG_OMNI)] = CFG_OMNI
    cf.update(configs or {})
    return core.Model(tx, {PH: copy.deepcopy(PREV)}, cf, {})


def gh(lock):
    return c.b2h(c.script_hash(lock))


def v1_reader(on):
    core.lock_kind = (lambda lock: "unknown" if REAL_LOCK_KIND(lock) == "sighash" else REAL_LOCK_KIND(lock)) if on else REAL_LOCK_KIND


def attempt(f):
    try:
        return {"ok": True, "result": f()}
    except core.SigsheetError as e:
        return {"ok": False, "refused": str(e)}


# ------------------------------------------------------------------ merge rules for groups the reader doesn't sign

def merge_v2(*models):
    """Version 2, section 7 rule 7: unknown-kind entries kept unchanged and unverified, the smaller bytes on a conflict."""
    out = core.merge(*models)
    groups = core.lock_groups(out)
    for m in models:
        for g, entries in m.sigs.items():
            if g in groups and groups[g]["kind"] == "unknown":
                for kh, sig in entries.items():
                    cur = out.sigs.setdefault(g, {}).get(kh)
                    if cur is None or c.h2b(sig) < c.h2b(cur):
                        out.sigs[g][kh] = sig
    return out


def merge_v3(*models):
    """Candidate: as version 2, but two different entries under one signer in a group the reader doesn't sign refuse
    the merge (the reader can't tell which one is valid); a reader that signs the kind resolves it by verifying."""
    out = core.merge(*models)
    groups = core.lock_groups(out)
    for m in models:
        for g, entries in m.sigs.items():
            if g in groups and groups[g]["kind"] == "unknown":
                for kh, sig in entries.items():
                    cur = out.sigs.setdefault(g, {}).get(kh)
                    if cur is not None and cur != sig:
                        raise core.SigsheetError(f"conflicting unverified entries for signer {kh[:12]}... in group {g[:12]}...")
                    out.sigs[g][kh] = sig
    return out


def ready_and_final(model):
    st = core.status(model)
    try:
        final = core.finalize(model)
        return {"status": st, "finalized": True, "lock_rules": core.lock_rule_check(final, model.prevs)}
    except core.SigsheetError as e:
        return {"status": st, "finalized": False, "why": str(e)}


def check_conflict_in_unsigned_group():
    m = spend([0, 1], [cell(1499.999, MS)])
    g_ms, g_sk = gh(MS), gh(SK)
    honest = m.copy()
    core.sign_group(honest, g_ms, K[0]["secret"])
    core.sign_group(honest, g_ms, K[1]["secret"])
    core.sign_group(honest, g_sk, K[3]["secret"])           # signed by a reader that signs the single-key lock
    junk = m.copy()
    junk.sigs = {g_sk: {K[3]["blake160"]: "0x" + "00" * 65}}
    v1_reader(True)
    a = merge_v2(honest, junk)
    a_rev = merge_v2(junk, honest)
    kept = a.sigs[g_sk][K[3]["blake160"]]
    b = attempt(lambda: merge_v3(honest, junk) and "merged")
    b_rev = attempt(lambda: merge_v3(junk, honest) and "merged")
    b_alone = merge_v3(honest)
    v1_reader(False)
    rep = {"v2_rule_7": {"entry_kept": "65 zero bytes" if kept == "0x" + "00" * 65 else "the valid signature",
                         "same_in_both_orders": a.sigs == a_rev.sigs,
                         "later_reader_that_signs_the_kind": ready_and_final(a)},
           "candidate_rule": {"merge_honest_and_junk": b, "reverse_order": b_rev,
                              "merge_honest_alone_then_later_reader": ready_and_final(b_alone),
                              "a_reader_that_signs_the_kind_merges_both": ready_and_final(core.merge(honest, junk))}}
    return rep


# ------------------------------------------------------------------ configs

def v2_configs(model):
    """Version 2, section 2.1: every config that hashes to its key is kept."""
    return {k: v for k, v in model.configs.items() if core.config_id(v) == k}


def v3_configs(model):
    """Candidate: a config is kept only when its 20-byte key occurs in some input's lock args (any offset), so a
    config for a kind the reader doesn't know (Omnilock: bytes 1-20) is kept and one for no input is refused."""
    args = [c.h2b(core.spent_output(model, i)[0]["lock"]["args"]) for i in range(len(model.tx["inputs"]))]
    return {k: v for k, v in model.configs.items() if core.config_id(v) == k and any(c.h2b(k) in a for a in args)}


def check_configs_for_no_input():
    junk = {}
    for _ in range(50):
        cfg = {"r": 0, "m": 2, "keys": [key()["blake160"] for _ in range(3)]}
        junk[core.config_id(cfg)] = cfg
    m = spend([0, 2], [cell(1299.999, MS)], configs=junk)
    m0 = spend([0, 2], [cell(1299.999, MS)])
    size = lambda mod: len(fmt_c.encode(mod))  # noqa: E731
    return {"configs_in_file": len(m.configs), "file_bytes_without_junk": size(m0), "file_bytes_with_50_junk_configs": size(m),
            "unsigned_id_unchanged": m.unsigned_id() == m0.unsigned_id(),
            "v2_kept": len(v2_configs(m)), "candidate_kept": len(v3_configs(m)),
            "candidate_keeps_the_omnilock_config": core.config_id(CFG_OMNI) in v3_configs(m),
            "candidate_keeps_the_multisig_config": core.config_id(CFG) in v3_configs(m),
            "today_prototype_reader": attempt(lambda: core.validate(m) and "accepted")}


# ------------------------------------------------------------------ Omnilock's multisig mode next to the multisig

def check7_v2(model):
    """Version 2, section 4 check 7, applied to the kinds the reader signs (the code hash says which)."""
    out = []
    for g in core.lock_groups(model).values():
        if g["kind"] == "multisig":
            core.group_config(model, g)
            out.append("multisig: config found")
        else:
            out.append(f"{g['kind']}: not a multisig group the reader signs; carried")
    return out


def check_omnilock_group_carried():
    m = spend([0, 2], [cell(1299.999, MS)])
    core.sign_group(m, gh(MS), K[0]["secret"])
    core.sign_group(m, gh(MS), K[1]["secret"])
    part = core.finalize(m, require_all=False)
    args = c.h2b(OMNI["args"])
    return {"omnilock_args_bytes": len(args), "auth_flag": args[0], "key_at_bytes_1_to_20": c.b2h(args[1:21]) == core.config_id(CFG_OMNI),
            "args_0_to_20_would_find_it": c.b2h(args[:20]) in m.configs,
            "today_prototype_reader": attempt(lambda: core.validate(m) and "accepted"),
            "v2_check_7": attempt(lambda: check7_v2(m)), "v2_config_rule_keeps_it": core.config_id(CFG_OMNI) in v2_configs(m),
            "candidate_config_rule_keeps_it": core.config_id(CFG_OMNI) in v3_configs(m),
            "partial_finalize": {"multisig_witness_written": part["witnesses"][0] != "0x", "omnilock_witness_left_as_template": part["witnesses"][1] == "0x",
                                 "multisig_lock_rules": core.lock_rule_check({**part, "witnesses": [part["witnesses"][0], c.b2h(c.witness_args(b""))]}, m.prevs).get(gh(MS))}}


def check_single_key_args_length():
    m = spend([4], [cell(99.999, SK)])
    g = core.lock_groups(m)[gh(SK32)]
    msg = core.group_message(m, g)
    m.sigs = {gh(SK32): {K[7]["blake160"]: c.b2h(c.sign(msg, c.h2b(K[7]["secret"])))}}
    ver, dropped = core.verified_sigs(m)
    return {"args_bytes": len(c.h2b(SK32["args"])), "today_prototype_reader": attempt(lambda: core.validate(m)),
            "signature_by_the_key": "dropped" if dropped else "kept", "drop_reason": dropped[0][2] if dropped else None,
            "candidate_check_7": "refused: a single-key group's args must be 20 bytes (secp256k1_blake160_sighash_all.c L106-L107)"}


# ------------------------------------------------------------------ what a signer is shown

def show(model, rules):
    tx = model.tx
    ins = [core.spent_output(model, i) for i in range(len(tx["inputs"]))]
    ms_locks = [o["lock"] for o, _ in ins if core.lock_kind(o["lock"]) == "multisig"]
    lines = []
    for i, (o, d) in enumerate(ins):
        t = o.get("type")
        line = f"input {i}: {int(o['capacity'], 16) / CKB} CKB, lock {o['lock']['args'][:14]}..., type {t['code_hash'][:12] + '...' if t else None}"
        if rules == "candidate":
            line += f", data {len(c.h2b(d))} bytes, data hash {c.b2h(c.ckbhash(c.h2b(d)))[:14]}..."
            if t and (t["code_hash"], t["hash_type"]) in TOKENS and len(c.h2b(d)) >= 16:
                line += f", {TOKENS[(t['code_hash'], t['hash_type'])]} amount {int.from_bytes(c.h2b(d)[:16], 'little'):,}"
        lines.append(line)
    in_locks = [o["lock"] for o, _ in ins]
    for j, o in enumerate(tx["outputs"]):
        d = c.h2b(tx["outputs_data"][j])
        plain = o.get("type") is None and not d
        if rules == "v2":
            label = "change" if plain and o["lock"] in ms_locks else "payment"
        else:
            label = f"back to the lock of input {in_locks.index(o['lock'])}" if plain and o["lock"] in in_locks else "payment"
        lines.append(f"output {j}: {int(o['capacity'], 16) / CKB} CKB, lock {o['lock']['args'][:14]}..., type {o['type']}, data {len(d)} bytes: {label}")
    if rules == "candidate":
        out_types = [o.get("type") for o in tx["outputs"]]
        for i, (o, d) in enumerate(ins):
            t = o.get("type")
            if t and t not in out_types:
                lines.append(f"warning: input {i}'s type script {t['code_hash'][:12]}... appears on no output: its cell is consumed"
                             + (f" ({TOKENS[(t['code_hash'], t['hash_type'])]} amount {int.from_bytes(c.h2b(d)[:16], 'little'):,} leaves)" if (t['code_hash'], t['hash_type']) in TOKENS else ""))
    fee = sum(int(o["capacity"], 16) for o, _ in ins) - sum(int(o["capacity"], 16) for o in tx["outputs"])
    lines.append(f"fee: {fee / CKB} CKB")
    return lines


def check_token_display():
    burn = spend([0, 3], [cell(1199.999, MS)])
    burn_data = c.h2b(PREV["outputs_data"][3])
    mixed = spend([0, 1], [cell(100, OTHER), cell(399.999, SK), cell(1000, MS)])
    return {"token_spent_with_no_token_output": {"v2": show(burn, "v2"), "candidate": show(burn, "candidate"), "token_data_bytes": len(burn_data)},
            "single_key_change_in_a_mixed_transaction": {"v2": show(mixed, "v2"), "candidate": show(mixed, "candidate")}}


def main():
    rep = {"conditions": "offline; the design-stage prototype unchanged; ephemeral keys", "previous_tx": PH,
           "conflict_in_unsigned_group": check_conflict_in_unsigned_group(),
           "configs_for_no_input": check_configs_for_no_input(),
           "omnilock_group_carried": check_omnilock_group_carried(),
           "single_key_args_length": check_single_key_args_length(),
           "token_display": check_token_display()}
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
