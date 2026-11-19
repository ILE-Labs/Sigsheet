"""The CKB types, their Molecule encoding, and strict decoding.

Layouts follow RFC 0008 (https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0008-serialization/0008-serialization.md):
integers little-endian; a struct is its fields in order with nothing between them; a fixvec is a u32 item count and
the items; a dynvec and a table are a u32 total size, one u32 offset per item, then the items; an option is empty or
its item. The types are those of ckb v0.210.0's schema
(https://github.com/nervosnetwork/ckb/blob/2592ddf0502cd4adfe886db893cccc866db3c60f/util/gen-types/schemas/blockchain.mol#L1-L118).

Decoding is strict: a table must have exactly its schema's fields (Molecule's non-compatible mode, as the locks read
`WitnessArgs`), every size and offset must be consistent, and nothing may follow the last item.
"""

from dataclasses import dataclass

from .hashing import ckbhash

# Hash type names and their bytes: data 0, type 1, data1 2, data2 4
# (https://github.com/nervosnetwork/ckb/blob/2592ddf0502cd4adfe886db893cccc866db3c60f/rpc/README.md#L7235-L7250).
HASH_TYPES = {"data": 0, "type": 1, "data1": 2, "data2": 4}
HASH_TYPE_NAMES = {v: k for k, v in HASH_TYPES.items()}
DEP_TYPES = {"code": 0, "dep_group": 1}
DEP_TYPE_NAMES = {v: k for k, v in DEP_TYPES.items()}

HEADER_SIZE = 208
OUT_POINT_SIZE = 36
CELL_INPUT_SIZE = 44
CELL_DEP_SIZE = 37


class MoleculeError(ValueError):
    """Bytes that aren't a well-formed encoding of the expected type."""


@dataclass(frozen=True, slots=True)
class Script:
    code_hash: bytes
    hash_type: str
    args: bytes


@dataclass(frozen=True, slots=True)
class OutPoint:
    tx_hash: bytes
    index: int


@dataclass(frozen=True, slots=True)
class CellInput:
    since: int
    previous_output: OutPoint


@dataclass(frozen=True, slots=True)
class CellOutput:
    capacity: int
    lock: Script
    type: Script | None


@dataclass(frozen=True, slots=True)
class CellDep:
    out_point: OutPoint
    dep_type: str


@dataclass(frozen=True, slots=True)
class RawTransaction:
    version: int
    cell_deps: tuple[CellDep, ...]
    header_deps: tuple[bytes, ...]
    inputs: tuple[CellInput, ...]
    outputs: tuple[CellOutput, ...]
    outputs_data: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class Transaction:
    raw: RawTransaction
    witnesses: tuple[bytes, ...]


@dataclass(frozen=True, slots=True)
class Header:
    version: int
    compact_target: int
    timestamp: int
    number: int
    epoch: int
    parent_hash: bytes
    transactions_root: bytes
    proposals_hash: bytes
    extra_hash: bytes
    dao: bytes
    nonce: int


@dataclass(frozen=True, slots=True)
class WitnessArgs:
    lock: bytes | None = None
    input_type: bytes | None = None
    output_type: bytes | None = None


# ------------------------------------------------------------------ encoding


def uint(n: int, size: int) -> bytes:
    if not 0 <= n < 1 << (8 * size):
        raise MoleculeError(f"{n} doesn't fit in {size} bytes")
    return n.to_bytes(size, "little")


def fixed(b: bytes, size: int) -> bytes:
    if len(b) != size:
        raise MoleculeError(f"expected {size} bytes, got {len(b)}")
    return b


def encode_bytes(b: bytes) -> bytes:
    return uint(len(b), 4) + b


def fixvec(items: list[bytes]) -> bytes:
    return uint(len(items), 4) + b"".join(items)


def dynvec(items: list[bytes]) -> bytes:
    """A dynvec or a table: total size, one offset per item, then the items."""
    offset = 4 + 4 * len(items)
    offsets = []
    for item in items:
        offsets.append(uint(offset, 4))
        offset += len(item)
    return uint(offset, 4) + b"".join(offsets) + b"".join(items)


def encode_script(s: Script) -> bytes:
    return dynvec([fixed(s.code_hash, 32), bytes([HASH_TYPES[s.hash_type]]), encode_bytes(s.args)])


def encode_out_point(o: OutPoint) -> bytes:
    return fixed(o.tx_hash, 32) + uint(o.index, 4)


def encode_cell_input(i: CellInput) -> bytes:
    return uint(i.since, 8) + encode_out_point(i.previous_output)


def encode_cell_output(o: CellOutput) -> bytes:
    return dynvec([uint(o.capacity, 8), encode_script(o.lock), b"" if o.type is None else encode_script(o.type)])


def encode_cell_dep(d: CellDep) -> bytes:
    return encode_out_point(d.out_point) + bytes([DEP_TYPES[d.dep_type]])


def encode_raw_transaction(t: RawTransaction) -> bytes:
    return dynvec(
        [
            uint(t.version, 4),
            fixvec([encode_cell_dep(d) for d in t.cell_deps]),
            fixvec([fixed(h, 32) for h in t.header_deps]),
            fixvec([encode_cell_input(i) for i in t.inputs]),
            dynvec([encode_cell_output(o) for o in t.outputs]),
            dynvec([encode_bytes(d) for d in t.outputs_data]),
        ]
    )


def encode_transaction(t: Transaction) -> bytes:
    return dynvec([encode_raw_transaction(t.raw), dynvec([encode_bytes(w) for w in t.witnesses])])


def encode_header(h: Header) -> bytes:
    """`RawHeader` then the 16-byte nonce, a 208-byte struct."""
    return (
        uint(h.version, 4)
        + uint(h.compact_target, 4)
        + uint(h.timestamp, 8)
        + uint(h.number, 8)
        + uint(h.epoch, 8)
        + fixed(h.parent_hash, 32)
        + fixed(h.transactions_root, 32)
        + fixed(h.proposals_hash, 32)
        + fixed(h.extra_hash, 32)
        + fixed(h.dao, 32)
        + uint(h.nonce, 16)
    )


def encode_witness_args(w: WitnessArgs) -> bytes:
    def opt(b: bytes | None) -> bytes:
        return b"" if b is None else encode_bytes(b)

    return dynvec([opt(w.lock), opt(w.input_type), opt(w.output_type)])


def encode_out_point_vec(points: list[OutPoint]) -> bytes:
    return fixvec([encode_out_point(p) for p in points])


def script_hash(s: Script) -> bytes:
    return ckbhash(encode_script(s))


def transaction_hash(t: RawTransaction) -> bytes:
    """The hash of the raw transaction, without witnesses (RFC 0022 L392-L403)."""
    return ckbhash(encode_raw_transaction(t))


def header_hash(h: Header) -> bytes:
    return ckbhash(encode_header(h))


# ------------------------------------------------------------------ strict decoding


def read_uint(b: bytes) -> int:
    return int.from_bytes(b, "little")


def _offsets(b: bytes) -> list[bytes]:
    """The items of a dynvec or the fields of a table, with every size and offset checked."""
    if len(b) < 4:
        raise MoleculeError("shorter than a size field")
    total = read_uint(b[:4])
    if total != len(b):
        raise MoleculeError(f"size field says {total}, the bytes are {len(b)}")
    if total == 4:
        return []
    if total < 8:
        raise MoleculeError("no room for the first offset")
    first = read_uint(b[4:8])
    if first % 4 or first < 8 or first > total:
        raise MoleculeError(f"bad first offset {first}")
    count = first // 4 - 1
    offsets = [read_uint(b[4 + 4 * i : 8 + 4 * i]) for i in range(count)] + [total]
    for i in range(count):
        if offsets[i] > offsets[i + 1]:
            raise MoleculeError("offsets aren't in order")
    return [b[offsets[i] : offsets[i + 1]] for i in range(count)]


def table(b: bytes, fields: int) -> list[bytes]:
    items = _offsets(b)
    if len(items) != fields:
        raise MoleculeError(f"a table with {len(items)} fields where the schema has {fields}")
    return items


def decode_bytes(b: bytes) -> bytes:
    if len(b) < 4 or read_uint(b[:4]) != len(b) - 4:
        raise MoleculeError("bad Bytes")
    return b[4:]


def decode_bytes_opt(b: bytes) -> bytes | None:
    return None if b == b"" else decode_bytes(b)


def decode_fixvec(b: bytes, size: int) -> list[bytes]:
    if len(b) < 4:
        raise MoleculeError("shorter than a count field")
    count = read_uint(b[:4])
    if len(b) != 4 + count * size:
        raise MoleculeError(f"a fixvec of {count} items of {size} bytes can't be {len(b)} bytes")
    return [b[4 + i * size : 4 + (i + 1) * size] for i in range(count)]


def decode_script(b: bytes) -> Script:
    code_hash, hash_type, args = table(b, 3)
    if len(code_hash) != 32 or len(hash_type) != 1 or hash_type[0] not in HASH_TYPE_NAMES:
        raise MoleculeError("bad Script")
    return Script(code_hash, HASH_TYPE_NAMES[hash_type[0]], decode_bytes(args))


def decode_out_point(b: bytes) -> OutPoint:
    if len(b) != OUT_POINT_SIZE:
        raise MoleculeError("bad OutPoint")
    return OutPoint(b[:32], read_uint(b[32:]))


def decode_cell_input(b: bytes) -> CellInput:
    if len(b) != CELL_INPUT_SIZE:
        raise MoleculeError("bad CellInput")
    return CellInput(read_uint(b[:8]), decode_out_point(b[8:]))


def decode_cell_output(b: bytes) -> CellOutput:
    capacity, lock, type_ = table(b, 3)
    if len(capacity) != 8:
        raise MoleculeError("bad capacity")
    return CellOutput(read_uint(capacity), decode_script(lock), decode_script(type_) if type_ else None)


def decode_cell_dep(b: bytes) -> CellDep:
    if len(b) != CELL_DEP_SIZE or b[36] not in DEP_TYPE_NAMES:
        raise MoleculeError("bad CellDep")
    return CellDep(decode_out_point(b[:36]), DEP_TYPE_NAMES[b[36]])


def decode_raw_transaction(b: bytes) -> RawTransaction:
    version, deps, header_deps, inputs, outputs, outputs_data = table(b, 6)
    if len(version) != 4:
        raise MoleculeError("bad version")
    return RawTransaction(
        read_uint(version),
        tuple(decode_cell_dep(d) for d in decode_fixvec(deps, CELL_DEP_SIZE)),
        tuple(decode_fixvec(header_deps, 32)),
        tuple(decode_cell_input(i) for i in decode_fixvec(inputs, CELL_INPUT_SIZE)),
        tuple(decode_cell_output(o) for o in _offsets(outputs)),
        tuple(decode_bytes(d) for d in _offsets(outputs_data)),
    )


def decode_transaction(b: bytes) -> Transaction:
    raw, witnesses = table(b, 2)
    return Transaction(decode_raw_transaction(raw), tuple(decode_bytes(w) for w in _offsets(witnesses)))


def decode_header(b: bytes) -> Header:
    if len(b) != HEADER_SIZE:
        raise MoleculeError(f"a header is {HEADER_SIZE} bytes, not {len(b)}")
    return Header(
        read_uint(b[0:4]),
        read_uint(b[4:8]),
        read_uint(b[8:16]),
        read_uint(b[16:24]),
        read_uint(b[24:32]),
        b[32:64],
        b[64:96],
        b[96:128],
        b[128:160],
        b[160:192],
        read_uint(b[192:208]),
    )


def decode_witness_args(b: bytes) -> WitnessArgs:
    lock, input_type, output_type = table(b, 3)
    return WitnessArgs(decode_bytes_opt(lock), decode_bytes_opt(input_type), decode_bytes_opt(output_type))


def decode_out_point_vec(b: bytes) -> list[OutPoint]:
    return [decode_out_point(p) for p in decode_fixvec(b, OUT_POINT_SIZE)]
