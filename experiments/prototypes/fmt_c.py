"""Path C (with D merged), as revised: one JSON file in RFC 8785 canonical form.

    {
      "context":          {tx_hash: previous raw transaction, RPC JSON, no witnesses},
      "multisig_configs": {blake160(multisig script): {"public_key_hashes": [...], "require_first_n": R,
                                                      "threshold": M}},
      "signatures":       {lock script hash: {signer key hash: 65-byte signature}},
      "transaction":      the transaction, CKB RPC JSON; witnesses are templates (core.py),
      "version":          "0x1"
    }

Choices this prototype makes where the path file leaves room (prototypes/README.md says why):
- `signatures` is keyed by the lock script hash (the lock group), not by lock args: two groups can share args
  (the same multisig script under two deployments) and need separate signatures (X2 case S10).
- `multisig_configs` has no `since`: the since is in the lock args, which the signer reads from the input cell.
- `context` is a map keyed by transaction hash (no duplicates; each entry checked by hashing).
"""
import json

import core
from core import SigsheetError
from record import wrap

VERSION = "0x1"
TOP = {"context", "multisig_configs", "signatures", "transaction", "version"}
TX_FIELDS = set(core.RAW_FIELDS) | {"witnesses"}
CFG_ALIAS = {"r": "require_first_n", "m": "threshold", "keys": "public_key_hashes"}


def to_doc(model):
    return {
        "version": VERSION,
        "transaction": model.tx,
        "context": model.prevs,
        "multisig_configs": {cid: {"public_key_hashes": cfg["keys"], "require_first_n": cfg["r"],
                                   "threshold": cfg["m"]} for cid, cfg in model.configs.items()},
        "signatures": {gh: dict(v) for gh, v in model.sigs.items() if v},
    }


def encode(model) -> bytes:
    return core.canon(to_doc(model)).encode("ascii")


def decode(data: bytes, check=True):
    """Parse, check the schema and canonical form, return the model. check: also run core.validate."""
    try:
        doc = json.loads(data.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SigsheetError(f"not ASCII JSON: {e}")
    if not isinstance(doc, dict) or set(doc) != TOP:
        raise SigsheetError(f"top-level fields must be exactly {sorted(TOP)}")
    if doc["version"] != VERSION:
        raise SigsheetError(f"unknown version {doc['version']!r}")
    tx = doc["transaction"]
    if not isinstance(tx, dict) or set(tx) != TX_FIELDS:
        raise SigsheetError("transaction must have exactly the RPC fields, without a hash")
    for h, p in doc["context"].items():
        if set(p) != set(core.RAW_FIELDS):
            raise SigsheetError(f"context entry {h[:12]}... must be a raw transaction without witnesses")
    configs = {}
    for cid, cfg in doc["multisig_configs"].items():
        if set(cfg) != {"public_key_hashes", "require_first_n", "threshold"}:
            raise SigsheetError("multisig config fields")
        if not all(isinstance(cfg[k], int) for k in ("require_first_n", "threshold")):
            raise SigsheetError("R and M must be integers")
        configs[cid] = {"r": cfg["require_first_n"], "m": cfg["threshold"], "keys": cfg["public_key_hashes"]}
    model = core.Model(tx, doc["context"], configs, doc["signatures"])
    if encode(model) != data:
        raise SigsheetError("not in canonical form")
    if check:
        core.validate(model)
    return model


class View:
    """The model as a signer's code sees the decoded file, with every field read recorded."""

    def __init__(self, data: bytes, log: set):
        doc = json.loads(data.decode("ascii"))
        d = wrap(doc, "", log)
        self.tx = d["transaction"]
        self.prevs = d["context"]
        self.configs = wrap(doc["multisig_configs"], "multisig_configs", log, None, CFG_ALIAS)
        log.add("multisig_configs")
        self.sigs = {}


def messages_from_file(data: bytes, log: set):
    """Compute every group's message from the file, recording the fields read."""
    v = View(data, log)
    out = {}
    for gh, g in core.lock_groups(v).items():
        if g["kind"] in ("multisig", "sighash"):
            out[gh] = core.c.b2h(core.group_message(v, g))
    return out
