"""CKB RPC JSON to and from the CKB types, with strict hex rules.

Integers are `0x` and lowercase hex digits with no redundant leading zero (`0x0` is zero); bytes are `0x` and two
lowercase hex digits per byte (`0x` is empty). The node also accepts uppercase on input
(https://github.com/nervosnetwork/ckb/blob/2592ddf0502cd4adfe886db893cccc866db3c60f/util/jsonrpc-types/src/uints.rs#L56-L95);
the Sigsheet form allows lowercase only. Every object must have exactly its fields.
"""

from .merkle import TransactionProof
from .molecule import (
    DEP_TYPES,
    HASH_TYPES,
    CellDep,
    CellInput,
    CellOutput,
    Header,
    OutPoint,
    RawTransaction,
    Script,
    Transaction,
    header_hash,
)

_HEX = set("0123456789abcdef")

RAW_FIELDS = ("version", "cell_deps", "header_deps", "inputs", "outputs", "outputs_data")
TRANSACTION_FIELDS = (*RAW_FIELDS, "witnesses")
HEADER_FIELDS = (
    "compact_target",
    "dao",
    "epoch",
    "extra_hash",
    "nonce",
    "number",
    "parent_hash",
    "proposals_hash",
    "timestamp",
    "transactions_root",
    "version",
)


class JsonShapeError(ValueError):
    """A JSON value that isn't the expected CKB RPC form."""

    def __init__(self, path: str, message: str):
        super().__init__(f"{path}: {message}")
        self.path = path


def expect_object(v, path: str, fields) -> dict:
    if not isinstance(v, dict):
        raise JsonShapeError(path, "must be an object")
    if set(v) != set(fields):
        raise JsonShapeError(path, f"must have exactly the fields {sorted(fields)}")
    return v


def expect_list(v, path: str) -> list:
    if not isinstance(v, list):
        raise JsonShapeError(path, "must be an array")
    return v


def parse_uint(v, bits: int, path: str) -> int:
    if not isinstance(v, str) or not v.startswith("0x") or len(v) < 3 or not set(v[2:]) <= _HEX:
        raise JsonShapeError(path, "must be a 0x-prefixed lowercase hex integer")
    if len(v) > 3 and v[2] == "0":
        raise JsonShapeError(path, "has a redundant leading zero")
    n = int(v[2:], 16)
    if n >= 1 << bits:
        raise JsonShapeError(path, f"doesn't fit in {bits} bits")
    return n


def parse_bytes(v, path: str, size: int | None = None) -> bytes:
    if not isinstance(v, str) or not v.startswith("0x") or len(v) % 2 or not set(v[2:]) <= _HEX:
        raise JsonShapeError(path, "must be 0x and two lowercase hex digits per byte")
    b = bytes.fromhex(v[2:])
    if size is not None and len(b) != size:
        raise JsonShapeError(path, f"must be {size} bytes")
    return b


def fmt_uint(n: int) -> str:
    return hex(n)


def fmt_bytes(b: bytes) -> str:
    return "0x" + b.hex()


def script_from(v, path: str) -> Script:
    v = expect_object(v, path, ("code_hash", "hash_type", "args"))
    if v["hash_type"] not in HASH_TYPES:
        raise JsonShapeError(f"{path}.hash_type", f"must be one of {sorted(HASH_TYPES)}")
    return Script(
        parse_bytes(v["code_hash"], f"{path}.code_hash", 32), v["hash_type"], parse_bytes(v["args"], f"{path}.args")
    )


def script_to(s: Script) -> dict:
    return {"code_hash": fmt_bytes(s.code_hash), "hash_type": s.hash_type, "args": fmt_bytes(s.args)}


def out_point_from(v, path: str) -> OutPoint:
    v = expect_object(v, path, ("tx_hash", "index"))
    return OutPoint(parse_bytes(v["tx_hash"], f"{path}.tx_hash", 32), parse_uint(v["index"], 32, f"{path}.index"))


def out_point_to(o: OutPoint) -> dict:
    return {"tx_hash": fmt_bytes(o.tx_hash), "index": fmt_uint(o.index)}


def cell_input_from(v, path: str) -> CellInput:
    v = expect_object(v, path, ("since", "previous_output"))
    return CellInput(
        parse_uint(v["since"], 64, f"{path}.since"), out_point_from(v["previous_output"], f"{path}.previous_output")
    )


def cell_input_to(i: CellInput) -> dict:
    return {"since": fmt_uint(i.since), "previous_output": out_point_to(i.previous_output)}


def cell_output_from(v, path: str) -> CellOutput:
    v = expect_object(v, path, ("capacity", "lock", "type"))
    type_ = None if v["type"] is None else script_from(v["type"], f"{path}.type")
    return CellOutput(parse_uint(v["capacity"], 64, f"{path}.capacity"), script_from(v["lock"], f"{path}.lock"), type_)


def cell_output_to(o: CellOutput) -> dict:
    return {
        "capacity": fmt_uint(o.capacity),
        "lock": script_to(o.lock),
        "type": None if o.type is None else script_to(o.type),
    }


def cell_dep_from(v, path: str) -> CellDep:
    v = expect_object(v, path, ("out_point", "dep_type"))
    if v["dep_type"] not in DEP_TYPES:
        raise JsonShapeError(f"{path}.dep_type", f"must be one of {sorted(DEP_TYPES)}")
    return CellDep(out_point_from(v["out_point"], f"{path}.out_point"), v["dep_type"])


def cell_dep_to(d: CellDep) -> dict:
    return {"out_point": out_point_to(d.out_point), "dep_type": d.dep_type}


def _raw_from(v: dict, path: str) -> RawTransaction:
    return RawTransaction(
        parse_uint(v["version"], 32, f"{path}.version"),
        tuple(
            cell_dep_from(d, f"{path}.cell_deps[{i}]")
            for i, d in enumerate(expect_list(v["cell_deps"], f"{path}.cell_deps"))
        ),
        tuple(
            parse_bytes(h, f"{path}.header_deps[{i}]", 32)
            for i, h in enumerate(expect_list(v["header_deps"], f"{path}.header_deps"))
        ),
        tuple(
            cell_input_from(x, f"{path}.inputs[{i}]") for i, x in enumerate(expect_list(v["inputs"], f"{path}.inputs"))
        ),
        tuple(
            cell_output_from(o, f"{path}.outputs[{i}]")
            for i, o in enumerate(expect_list(v["outputs"], f"{path}.outputs"))
        ),
        tuple(
            parse_bytes(d, f"{path}.outputs_data[{i}]")
            for i, d in enumerate(expect_list(v["outputs_data"], f"{path}.outputs_data"))
        ),
    )


def raw_transaction_from(v, path: str) -> RawTransaction:
    """A raw transaction: exactly the six fields of `RawTransaction`, no witnesses, no hash."""
    return _raw_from(expect_object(v, path, RAW_FIELDS), path)


def raw_transaction_to(t: RawTransaction) -> dict:
    return {
        "version": fmt_uint(t.version),
        "cell_deps": [cell_dep_to(d) for d in t.cell_deps],
        "header_deps": [fmt_bytes(h) for h in t.header_deps],
        "inputs": [cell_input_to(i) for i in t.inputs],
        "outputs": [cell_output_to(o) for o in t.outputs],
        "outputs_data": [fmt_bytes(d) for d in t.outputs_data],
    }


def transaction_from(v, path: str) -> Transaction:
    """A transaction as `send_transaction` takes it: the six raw fields and `witnesses`, no hash."""
    v = expect_object(v, path, TRANSACTION_FIELDS)
    witnesses = tuple(
        parse_bytes(w, f"{path}.witnesses[{i}]") for i, w in enumerate(expect_list(v["witnesses"], f"{path}.witnesses"))
    )
    return Transaction(_raw_from(v, path), witnesses)


def transaction_to(t: Transaction) -> dict:
    return {**raw_transaction_to(t.raw), "witnesses": [fmt_bytes(w) for w in t.witnesses]}


def header_from(v, path: str) -> Header:
    """A header in RPC JSON without its hash: exactly the eleven fields of `Header`."""
    v = expect_object(v, path, HEADER_FIELDS)
    return Header(
        parse_uint(v["version"], 32, f"{path}.version"),
        parse_uint(v["compact_target"], 32, f"{path}.compact_target"),
        parse_uint(v["timestamp"], 64, f"{path}.timestamp"),
        parse_uint(v["number"], 64, f"{path}.number"),
        parse_uint(v["epoch"], 64, f"{path}.epoch"),
        parse_bytes(v["parent_hash"], f"{path}.parent_hash", 32),
        parse_bytes(v["transactions_root"], f"{path}.transactions_root", 32),
        parse_bytes(v["proposals_hash"], f"{path}.proposals_hash", 32),
        parse_bytes(v["extra_hash"], f"{path}.extra_hash", 32),
        parse_bytes(v["dao"], f"{path}.dao", 32),
        parse_uint(v["nonce"], 128, f"{path}.nonce"),
    )


def header_to(h: Header) -> dict:
    return {
        "compact_target": fmt_uint(h.compact_target),
        "dao": fmt_bytes(h.dao),
        "epoch": fmt_uint(h.epoch),
        "extra_hash": fmt_bytes(h.extra_hash),
        "nonce": fmt_uint(h.nonce),
        "number": fmt_uint(h.number),
        "parent_hash": fmt_bytes(h.parent_hash),
        "proposals_hash": fmt_bytes(h.proposals_hash),
        "timestamp": fmt_uint(h.timestamp),
        "transactions_root": fmt_bytes(h.transactions_root),
        "version": fmt_uint(h.version),
    }


def header_view_from(v, path: str) -> Header:
    """A `HeaderView` (a node's `get_header` result): the header and its hash, which must match."""
    if not isinstance(v, dict) or "hash" not in v:
        raise JsonShapeError(path, "must be a header with its hash")
    header = header_from({k: x for k, x in v.items() if k != "hash"}, path)
    if header_hash(header) != parse_bytes(v["hash"], f"{path}.hash", 32):
        raise JsonShapeError(f"{path}.hash", "isn't the hash of the header")
    return header


def proof_from(v, path: str) -> TransactionProof:
    """A `TransactionProof`: `block_hash`, `proof` (`indices`, `lemmas`) and `witnesses_root`."""
    v = expect_object(v, path, ("block_hash", "proof", "witnesses_root"))
    p = expect_object(v["proof"], f"{path}.proof", ("indices", "lemmas"))
    return TransactionProof(
        parse_bytes(v["block_hash"], f"{path}.block_hash", 32),
        tuple(
            parse_uint(x, 32, f"{path}.proof.indices[{i}]")
            for i, x in enumerate(expect_list(p["indices"], f"{path}.proof.indices"))
        ),
        tuple(
            parse_bytes(x, f"{path}.proof.lemmas[{i}]", 32)
            for i, x in enumerate(expect_list(p["lemmas"], f"{path}.proof.lemmas"))
        ),
        parse_bytes(v["witnesses_root"], f"{path}.witnesses_root", 32),
    )


def proof_to(p: TransactionProof) -> dict:
    return {
        "block_hash": fmt_bytes(p.block_hash),
        "proof": {"indices": [fmt_uint(i) for i in p.indices], "lemmas": [fmt_bytes(x) for x in p.lemmas]},
        "witnesses_root": fmt_bytes(p.witnesses_root),
    }
