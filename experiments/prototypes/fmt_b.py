"""Path B, as revised (paths.md, path B): PSBT-style global and per-input maps, in JSON.

    {
      "global":  {"SIGSHEET_GLOBAL_VERSION": "0x1",
                  "SIGSHEET_GLOBAL_NETWORK_ID": genesis block hash,
                  "SIGSHEET_GLOBAL_RAW_TX": Molecule RawTransaction (hex)
                  [, "SIGSHEET_GLOBAL_WITNESSES": Molecule BytesVec of the witness templates (variant "B+w" only)]},
      "inputs":  [{"SIGSHEET_IN_PREVIOUS_TX": Molecule Transaction (hex),
                   "SIGSHEET_IN_MULTISIG_CONFIG": multisig script S|R|M|N|hashes (multisig inputs),
                   "SIGSHEET_IN_SINCE_REQUIREMENT": the args' since (28-byte args only),
                   "SIGSHEET_IN_PARTIAL_SIG": {signer key hash: signature} (first input of each group)}, ...],
      "outputs": [{} per output]
    }

B as revised carries no witnesses: its field table has the raw transaction and, once final, a per-input final
witness. So a B reader must assume the witness templates: one "0x" per input and nothing beyond the inputs.
The variant "B+w" adds SIGSHEET_GLOBAL_WITNESSES (X2 tests both). Choices where the path file leaves room:
the previous transaction is carried in full per input, as B's table says (so two inputs spending one previous
transaction carry it twice); the config on every multisig input; partial signatures on the first input of
each lock group only. Integers are 0x hex strings (B's revised canonical rule 5).
"""
import json

import core
import mol
from core import SigsheetError, c
from record import wrap

VERSION = "0x1"


def to_doc(model, network_id, with_witnesses):
    groups = core.lock_groups(model)
    first_of = {g["inputs"][0]: gh for gh, g in groups.items()}
    gl = {"SIGSHEET_GLOBAL_VERSION": VERSION, "SIGSHEET_GLOBAL_NETWORK_ID": network_id,
          "SIGSHEET_GLOBAL_RAW_TX": c.b2h(c.raw_transaction(model.tx))}
    if with_witnesses:
        gl["SIGSHEET_GLOBAL_WITNESSES"] = c.b2h(mol.enc_bytesvec([c.h2b(w) for w in model.tx["witnesses"]]))
    inputs = []
    for i, inp in enumerate(model.tx["inputs"]):
        prev = dict(model.prevs[inp["previous_output"]["tx_hash"]])
        prev["witnesses"] = []
        e = {"SIGSHEET_IN_PREVIOUS_TX": c.b2h(mol.enc_transaction(prev))}
        out, _ = core.spent_output(model, i)
        if core.lock_kind(out["lock"]) == "multisig":
            args = c.h2b(out["lock"]["args"])
            cfg = model.configs[c.b2h(args[:20])]
            e["SIGSHEET_IN_MULTISIG_CONFIG"] = c.b2h(core.script_of(cfg))
            if len(args) == 28:
                e["SIGSHEET_IN_SINCE_REQUIREMENT"] = hex(int.from_bytes(args[20:], "little"))
        gh = first_of.get(i)
        if gh is not None and model.sigs.get(gh):
            e["SIGSHEET_IN_PARTIAL_SIG"] = dict(model.sigs[gh])
        inputs.append(e)
    return {"global": gl, "inputs": inputs, "outputs": [{} for _ in model.tx["outputs"]]}


def encode(model, network_id, with_witnesses=False) -> bytes:
    return core.canon(to_doc(model, network_id, with_witnesses)).encode("ascii")


def parse_config(script_hex):
    b = c.h2b(script_hex)
    if len(b) < 4 or b[0] != 0 or len(b) != 4 + 20 * b[3]:
        raise SigsheetError("bad multisig script")
    info = c.parse_multisig_script(b)
    return {"r": info["require_first_n"], "m": info["threshold"], "keys": [c.b2h(k) for k in info["keys"]]}


def decode(data: bytes, check=True):
    """Returns (model, network_id, with_witnesses)."""
    doc = json.loads(data.decode("ascii"))
    if set(doc) != {"global", "inputs", "outputs"}:
        raise SigsheetError("top-level fields")
    gl = doc["global"]
    if gl.get("SIGSHEET_GLOBAL_VERSION") != VERSION:
        raise SigsheetError("version")
    with_w = "SIGSHEET_GLOBAL_WITNESSES" in gl
    tx = mol.raw_transaction(c.h2b(gl["SIGSHEET_GLOBAL_RAW_TX"]))
    if with_w:
        tx["witnesses"] = [c.b2h(mol.mbytes(x)) for x in mol.dynvec(c.h2b(gl["SIGSHEET_GLOBAL_WITNESSES"]))]
    else:
        tx["witnesses"] = ["0x"] * len(tx["inputs"])
    if len(doc["inputs"]) != len(tx["inputs"]) or len(doc["outputs"]) != len(tx["outputs"]):
        raise SigsheetError("per-input or per-output maps don't match the transaction")
    prevs, configs, sigs = {}, {}, {}
    for e in doc["inputs"]:
        p = mol.transaction(c.h2b(e["SIGSHEET_IN_PREVIOUS_TX"]))
        if p.pop("witnesses"):
            raise SigsheetError("this prototype carries previous transactions without witnesses")
        prevs[c.b2h(c.tx_hash(p))] = p
        if "SIGSHEET_IN_MULTISIG_CONFIG" in e:
            cfg = parse_config(e["SIGSHEET_IN_MULTISIG_CONFIG"])
            configs[core.config_id(cfg)] = cfg
    model = core.Model(tx, prevs, configs, {})
    groups = core.lock_groups(model)
    first_of = {g["inputs"][0]: gh for gh, g in groups.items()}
    for i, e in enumerate(doc["inputs"]):
        if "SIGSHEET_IN_PARTIAL_SIG" in e:
            if i not in first_of:
                raise SigsheetError("partial signatures must sit on the first input of their lock group")
            sigs[first_of[i]] = e["SIGSHEET_IN_PARTIAL_SIG"]
    model.sigs = sigs
    if encode(model, gl["SIGSHEET_GLOBAL_NETWORK_ID"], with_w) != data:
        raise SigsheetError("not in canonical form")
    if check:
        core.validate(model)
    return model, gl["SIGSHEET_GLOBAL_NETWORK_ID"], with_w


class View:
    """What a signer's code reads from a B file: field-level reads of the Molecule blobs."""

    def __init__(self, data: bytes, log: set):
        doc = json.loads(data.decode("ascii"))
        d = wrap(doc, "", log)
        gl = d["global"]
        self.tx = mol.raw_transaction(c.h2b(gl["SIGSHEET_GLOBAL_RAW_TX"]))
        if "SIGSHEET_GLOBAL_WITNESSES" in gl:
            self.tx["witnesses"] = [c.b2h(mol.mbytes(x)) for x in mol.dynvec(c.h2b(gl["SIGSHEET_GLOBAL_WITNESSES"]))]
        else:
            self.tx["witnesses"] = ["0x"] * len(self.tx["inputs"])
        self.prevs, self.configs, self.sigs = {}, {}, {}
        for e in d["inputs"]:
            p = mol.transaction(c.h2b(e["SIGSHEET_IN_PREVIOUS_TX"]))
            p.pop("witnesses")
            self.prevs[c.b2h(c.tx_hash(p))] = p
            if "SIGSHEET_IN_MULTISIG_CONFIG" in e:
                cfg = parse_config(e["SIGSHEET_IN_MULTISIG_CONFIG"])
                self.configs[core.config_id(cfg)] = cfg


def messages_from_file(data: bytes, log: set):
    v = View(data, log)
    return {gh: c.b2h(core.group_message(v, g)) for gh, g in core.lock_groups(v).items()
            if g["kind"] in ("multisig", "sighash")}
