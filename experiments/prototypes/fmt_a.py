"""Path A, as revised: a profile of CoBuild's BuildingPacketV1, Molecule as the canonical form.

BuildingPacket (union, id 0 = BuildingPacketV1), schemas from ckb-transaction-cobuild-poc `schemas/basic.mol`:
- message:         Message {actions: []}. The profile requires it empty (an unsigned message is a spoofing surface).
- payload:         Transaction. Witness templates as in core.py; a signed single-key input's first witness holds
                   its signature (single-key signatures have no action).
- resolved_inputs: {outputs: the spent outputs, which must equal the carried previous transactions' outputs byte
                   for byte; outputs_data: one empty Bytes per input} (A's revision; the data isn't repeated).
- change_output:   None (the profile maps losslessly onto C only without it).
- script_infos:    one ScriptInfo per multisig deployment the transaction spends from, describing MultisigAction
                   (name, url and schema as in doitian's PoC `multisig-lock-action.js`, plus the
                   `input_transactions` field; script_hash = hash of the lock script with empty args).
- lock_actions:    one Action per multisig lock group, in order of the group's first input:
                   script_info_hash, script_hash (the group's lock script hash), data = MultisigAction:
                     config {require_first_n: byte, threshold: byte, signer_pubkey_hashes: [20 bytes]},
                     signed [(pubkey_hash 20, signature 65)] sorted by pubkey_hash,
                     input_transactions [Transaction]: every previous transaction (no witnesses), sorted by hash,
                       in the first action only; empty in the others (A's file leaves where they go open).
Also `to_json_view`: A's 1:1 JSON view (Action.data stays opaque hex, as CoBuild treats it).
"""
import json

import core
import mol
from core import SigsheetError, c
from record import wrap

NAME = b"secp256k1_blake160_multisig_all"
URL = b"https://github.com/nervosnetwork/ckb-system-scripts/blob/master/c/secp256k1_blake160_multisig_all.c"
SCHEMA = b"""array PubkeyHash [byte; 20];
vector PubkeyHashVec <PubkeyHash>;
table MultisigConfig {
    require_first_n: byte,
    threshold: byte,
    signer_pubkey_hashes: PubkeyHashVec,
}
array Signature [byte; 65];
struct PubkeyHashSignaturePair {
    pubkey_hash: PubkeyHash,
    signature: Signature,
}
vector PubkeyHashSignaturePairVec <PubkeyHashSignaturePair>;
vector TransactionVec <Transaction>;
table MultisigAction {
    config: MultisigConfig,
    signed: PubkeyHashSignaturePairVec,
    input_transactions: TransactionVec,
}"""
MESSAGE_TYPE = b"MultisigAction"


def script_info(lock):
    sh = c.script_hash({"code_hash": lock["code_hash"], "hash_type": lock["hash_type"], "args": "0x"})
    return c.table([c.mol_bytes(NAME), c.mol_bytes(URL), sh, c.mol_bytes(SCHEMA), c.mol_bytes(MESSAGE_TYPE)])


def multisig_groups(model):
    return [(gh, g) for gh, g in core.lock_groups(model).items() if g["kind"] == "multisig"]


def enc_action_data(cfg, signed, prev_txs):
    for k, s in signed.items():
        if len(c.h2b(k)) != 20 or len(c.h2b(s)) != 65:
            raise SigsheetError("a building packet holds only 20-byte key hashes and 65-byte signatures")
    config = c.table([bytes([cfg["r"]]), bytes([cfg["m"]]), c.fixvec([c.h2b(k) for k in cfg["keys"]])])
    pairs = c.fixvec([c.h2b(k) + c.h2b(s) for k, s in sorted(signed.items())])
    txs = c.dynvec([mol.enc_transaction(dict(p, witnesses=[])) for p in prev_txs])
    return c.table([config, pairs, txs])


def encode(model) -> bytes:
    groups = core.lock_groups(model)
    ms = multisig_groups(model)
    if not ms:
        raise SigsheetError("the building-packet profile needs at least one multisig group")
    payload = dict(model.tx)
    payload["witnesses"] = list(model.tx["witnesses"])
    for gh, g in groups.items():
        if g["kind"] == "sighash" and model.sigs.get(gh):
            it, ot = core.template_parts(model, g)
            payload["witnesses"][g["inputs"][0]] = c.b2h(c.witness_args(c.h2b(next(iter(model.sigs[gh].values()))), it, ot))
    spent = [core.spent_output(model, i) for i in range(len(model.tx["inputs"]))]
    resolved = c.table([c.dynvec([c.cell_output(o) for o, _ in spent]), c.dynvec([c.mol_bytes(b"") for _ in spent])])
    infos = {}
    for _, g in ms:
        si = script_info(g["lock"])
        infos[c.ckbhash(si)] = si
    prevs_sorted = [model.prevs[h] for h in sorted(model.prevs)]
    actions = []
    for n, (gh, g) in enumerate(ms):
        cfg = core.group_config(model, g)
        data = enc_action_data(cfg, model.sigs.get(gh, {}), prevs_sorted if n == 0 else [])
        actions.append(c.table([c.ckbhash(script_info(g["lock"])), c.h2b(gh), c.mol_bytes(data)]))
    packet = c.table([
        c.table([c.dynvec([])]),                      # message: {actions: []}
        mol.enc_transaction(payload),                 # payload
        resolved,                                     # resolved_inputs
        b"",                                          # change_output: None
        c.dynvec([infos[h] for h in sorted(infos)]),  # script_infos
        c.dynvec(actions),                            # lock_actions
    ])
    return c.u32(0) + packet


def _parse(data: bytes):
    """Decode the packet into plain Python values (no profile checks)."""
    if len(data) < 4 or mol.u32(data) != 0:
        raise SigsheetError("not a BuildingPacket union with BuildingPacketV1 (id 0)")
    message, payload, resolved, change, infos, actions = mol.table(data[4:], 6)
    (msg_actions,) = mol.table(message, 1)
    out_list, data_list = mol.table(resolved, 2)
    acts = []
    for a in mol.dynvec(actions):
        sih, sh, d = mol.table(a, 3)
        config, signed, txs = mol.table(mol.mbytes(d), 3)
        r, m, keys = mol.table(config, 3)
        acts.append({
            "script_info_hash": c.b2h(sih), "script_hash": c.b2h(sh),
            "config": {"r": r[0], "m": m[0], "keys": [c.b2h(k) for k in mol.fixvec(keys, 20)]},
            "signed": [(c.b2h(p[:20]), c.b2h(p[20:])) for p in mol.fixvec(signed, 85)],
            "input_transactions": [mol.transaction(t) for t in mol.dynvec(txs)],
        })
    return {
        "message_actions": len(mol.dynvec(msg_actions)),
        "payload": mol.transaction(payload),
        "resolved_outputs": [mol.cell_output(o) for o in mol.dynvec(out_list)],
        "resolved_data": [c.b2h(mol.mbytes(x)) for x in mol.dynvec(data_list)],
        "change_output": mol.option(change),
        "script_infos": [c.b2h(x) for x in mol.dynvec(infos)],
        "actions": acts,
    }


def decode(data: bytes, check=True):
    """Profile-aware decoding: every profile rule is checked; returns the model."""
    try:
        p = _parse(data)
    except mol.MolError as e:
        raise SigsheetError(f"malformed Molecule: {e}")
    if p["message_actions"]:
        raise SigsheetError("profile: message must have no actions")
    if p["change_output"] is not None:
        raise SigsheetError("profile: change_output must be None")
    if not p["actions"]:
        raise SigsheetError("profile: no lock action")
    prevs = {}
    for t in p["actions"][0]["input_transactions"]:
        if t.pop("witnesses"):
            raise SigsheetError("profile: previous transactions carry no witnesses")
        prevs[c.b2h(c.tx_hash(t))] = t
    if any(a["input_transactions"] for a in p["actions"][1:]):
        raise SigsheetError("profile: previous transactions go in the first action only")
    configs = {}
    for a in p["actions"]:
        configs[core.config_id(a["config"])] = a["config"]
    tx = p["payload"]
    model = core.Model(tx, prevs, configs, {})
    groups = core.lock_groups(model)
    for i in range(len(tx["inputs"])):
        o, _ = core.spent_output(model, i)
        if p["resolved_outputs"][i] != o:
            raise SigsheetError(f"profile: resolved_inputs.outputs[{i}] differs from the carried previous transaction")
    if len(p["resolved_outputs"]) != len(tx["inputs"]) or any(d != "0x" for d in p["resolved_data"]) \
            or len(p["resolved_data"]) != len(tx["inputs"]):
        raise SigsheetError("profile: resolved_inputs must list every input, with empty data")
    sigs = {}
    for gh, g in groups.items():
        if g["kind"] == "sighash":
            w = c.h2b(tx["witnesses"][g["inputs"][0]])
            lock, it, ot = (None, None, None) if not w else c.parse_witness_args(w)
            if lock is not None:
                sigs[gh] = {g["lock"]["args"]: c.b2h(lock)}
    model.tx = core.template_from_final(tx, {gh: g for gh, g in groups.items() if g["kind"] == "sighash"})
    ms = [gh for gh, g in groups.items() if g["kind"] == "multisig"]
    if [a["script_hash"] for a in p["actions"]] != ms:
        raise SigsheetError("profile: one action per multisig group, in order of the group's first input")
    for a in p["actions"]:
        if a["signed"]:
            sigs[a["script_hash"]] = dict(a["signed"])
    model.sigs = sigs
    if encode(model) != data:
        raise SigsheetError("not in canonical form (or outside the profile)")
    if check:
        core.validate(model)
    return model


def to_json_view(data: bytes, expand_action_data=False):
    """A's 1:1 JSON view of the packet. Action.data stays hex unless expand_action_data (for the field log)."""
    if mol.u32(data) != 0:
        raise SigsheetError("not BuildingPacketV1")
    message, payload, resolved, change, infos, actions = mol.table(data[4:], 6)
    out_list, data_list = mol.table(resolved, 2)

    def info_json(x):
        name, url, sh, schema, mt = mol.table(x, 5)
        return {"name": mol.mbytes(name).decode(), "url": mol.mbytes(url).decode(), "script_hash": c.b2h(sh),
                "schema": mol.mbytes(schema).decode(), "message_type": mol.mbytes(mt).decode()}

    def action_json(a):
        sih, sh, d = mol.table(a, 3)
        out = {"script_info_hash": c.b2h(sih), "script_hash": c.b2h(sh), "data": c.b2h(mol.mbytes(d))}
        if expand_action_data:
            config, signed, txs = mol.table(mol.mbytes(d), 3)
            r, m, keys = mol.table(config, 3)
            out["data"] = {"config": {"require_first_n": r[0], "threshold": m[0],
                                      "signer_pubkey_hashes": [c.b2h(k) for k in mol.fixvec(keys, 20)]},
                           "signed": [{"pubkey_hash": c.b2h(p[:20]), "signature": c.b2h(p[20:])}
                                      for p in mol.fixvec(signed, 85)],
                           "input_transactions": [mol.transaction(t) for t in mol.dynvec(txs)]}
        return out

    return {"BuildingPacketV1": {
        "message": {"actions": [action_json(a) for a in mol.dynvec(mol.table(message, 1)[0])]},
        "payload": mol.transaction(payload),
        "resolved_inputs": {"outputs": [mol.cell_output(o) for o in mol.dynvec(out_list)],
                            "outputs_data": [c.b2h(mol.mbytes(x)) for x in mol.dynvec(data_list)]},
        "change_output": None if not change else hex(mol.u32(change)),
        "script_infos": [info_json(x) for x in mol.dynvec(infos)],
        "lock_actions": [action_json(a) for a in mol.dynvec(actions)],
    }}


CFG_ALIAS = {"r": "require_first_n", "m": "threshold", "keys": "signer_pubkey_hashes"}


class View:
    """What a profile-aware signer's code reads to compute the messages, recorded over the expanded JSON view."""

    def __init__(self, data: bytes, log: set):
        view = to_json_view(data, expand_action_data=True)
        d = wrap(view, "", log)["BuildingPacketV1"]
        self.tx = d["payload"]
        acts = d["lock_actions"]
        self.prevs = {}
        for t in acts[0]["data"]["input_transactions"]:
            self.prevs[c.b2h(c.tx_hash(t))] = t
        self.configs = {}
        for a in acts:
            cfg = a["data"]["config"]
            plain = {"r": cfg["require_first_n"], "m": cfg["threshold"], "keys": list(cfg["signer_pubkey_hashes"])}
            self.configs[core.config_id(plain)] = plain  # every config field was read (and logged) just above
        self.sigs = {}


def messages_from_file(data: bytes, log: set):
    v = View(data, log)
    return {gh: c.b2h(core.group_message(v, g)) for gh, g in core.lock_groups(v).items()
            if g["kind"] in ("multisig", "sighash")}
