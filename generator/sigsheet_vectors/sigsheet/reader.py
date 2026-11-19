"""Every reader check, in the specification's order; the first that fails refuses the file with its check id.

A file the reader accepts comes back with what the checks derived: each input's spent output, the lock groups in
order of their first input (each with its kind and, for multisig, its config), and the unsigned id. Signatures are
verified afterwards (`signatures.py`): a bad signature is dropped, not a reason to refuse the file.
"""

from dataclasses import dataclass

from ..ckb import dao, scripts
from ..ckb.hashing import hasher
from ..ckb.merkle import verify_transaction_proof
from ..ckb.molecule import (
    CellOutput,
    MoleculeError,
    Script,
    decode_witness_args,
    encode_witness_args,
    header_hash,
    script_hash,
    transaction_hash,
    uint,
)
from . import canonical
from .schema import MultisigConfig, SchemaError, Sheet, from_json

CARRIED_LIMIT = 255


class Refused(Exception):
    def __init__(self, check_id: str, detail: str):
        super().__init__(f"{check_id}: {detail}")
        self.check_id = check_id
        self.detail = detail


@dataclass(frozen=True, slots=True)
class Group:
    lock_hash: bytes
    lock: Script
    kind: str | None
    inputs: tuple[int, ...]
    config: MultisigConfig | None


@dataclass(frozen=True, slots=True)
class Accepted:
    sheet: Sheet
    groups: dict[bytes, Group]
    spent: tuple[tuple[CellOutput, bytes], ...]
    unsigned_id: bytes
    development_chain: bool


def unsigned_id(sheet: Sheet) -> bytes:
    """ckbhash of the transaction hash, then each witness template preceded by its length as a u64 (little-endian)."""
    h = hasher()
    h.update(transaction_hash(sheet.transaction.raw))
    for w in sheet.transaction.witnesses:
        h.update(uint(len(w), 8) + w)
    return h.digest()


def read(data: bytes, development_chain: bool = False) -> Accepted:
    """Run every check on a file's bytes. `development_chain` adds the code hashes of the local chain the recorded
    vectors come from (`scripts.DEVELOPMENT_CHAIN_LOCK_KINDS`)."""
    try:
        sheet = from_json(canonical.check(data))
    except (canonical.CanonicalError, SchemaError) as e:
        raise Refused(e.check_id, str(e)) from e
    return check(sheet, development_chain)


def _refuse_unless(ok: bool, check_id: str, detail: str) -> None:
    if not ok:
        raise Refused(check_id, detail)


def _spent(sheet: Sheet) -> tuple[tuple[CellOutput, bytes], ...]:
    raw = sheet.transaction.raw
    _refuse_unless(
        len(raw.outputs) == len(raw.outputs_data),
        "transaction.outputs-data",
        "outputs and outputs_data differ in length",
    )
    points = [i.previous_output for i in raw.inputs]
    _refuse_unless(
        len(set(points)) == len(points), "transaction.duplicate-input", "an out point appears twice among the inputs"
    )
    for h, prev in sheet.context.items():
        _refuse_unless(
            transaction_hash(prev) == h, "context.hash", f"context entry 0x{h.hex()} doesn't hash to its key"
        )
    spent = []
    for i, op in enumerate(points):
        prev = sheet.context.get(op.tx_hash)
        ok = prev is not None and op.index < len(prev.outputs) and op.index < len(prev.outputs_data)
        _refuse_unless(ok, "context.missing", f"input {i} spends an output the context doesn't hold")
        spent.append((prev.outputs[op.index], prev.outputs_data[op.index]))
    used = {op.tx_hash for op in points}
    _refuse_unless(set(sheet.context) <= used, "context.unused", "a context entry that no input spends")
    return tuple(spent)


def _headers(sheet: Sheet) -> None:
    for h, header in sheet.headers.items():
        _refuse_unless(header_hash(header) == h, "headers.hash", f"header 0x{h.hex()} doesn't hash to its key")
    deps = set(sheet.transaction.raw.header_deps)
    _refuse_unless(deps <= set(sheet.headers), "headers.missing", "a header dep without its header")
    _refuse_unless(set(sheet.headers) <= deps, "headers.unused", "a header that isn't a header dep")


def _groups(spent, development_chain: bool) -> dict[bytes, tuple[Script, str | None, list[int]]]:
    groups: dict[bytes, tuple[Script, str | None, list[int]]] = {}
    for i, (output, _) in enumerate(spent):
        h = script_hash(output.lock)
        if h not in groups:
            groups[h] = (output.lock, scripts.lock_kind(output.lock, development_chain), [])
        groups[h][2].append(i)
    for lock, kind, _ in groups.values():
        if kind == scripts.SINGLE_KEY:
            _refuse_unless(len(lock.args) == 20, "lock.single-key-args", f"single-key args of {len(lock.args)} bytes")
        if kind in scripts.MULTISIG_KINDS:
            _refuse_unless(len(lock.args) in (20, 28), "lock.multisig-args", f"multisig args of {len(lock.args)} bytes")
    return groups


def _configs(sheet: Sheet, spent, groups) -> None:
    for key, c in sheet.multisig_configs.items():
        n = len(c.public_key_hashes)
        ok = 1 <= n <= 255 and 1 <= c.threshold <= n and c.require_first_n <= c.threshold
        _refuse_unless(
            ok, "multisig-configs.values", f"config 0x{key.hex()}: R {c.require_first_n}, M {c.threshold}, N {n}"
        )
    for key, c in sheet.multisig_configs.items():
        ok = len(set(c.public_key_hashes)) == len(c.public_key_hashes)
        _refuse_unless(ok, "multisig-configs.repeated-key", f"config 0x{key.hex()} lists a member twice")
    for key, c in sheet.multisig_configs.items():
        _refuse_unless(c.key() == key, "multisig-configs.hash", f"config 0x{key.hex()} doesn't hash to its key")
    args = [output.lock.args for output, _ in spent]
    for key in sheet.multisig_configs:
        _refuse_unless(
            any(key in a for a in args), "multisig-configs.unused", f"config 0x{key.hex()} is in no input's lock args"
        )
    for lock, kind, _ in groups.values():
        if kind in scripts.MULTISIG_KINDS:
            ok = lock.args[:20] in sheet.multisig_configs
            _refuse_unless(ok, "multisig-configs.missing", f"no config for multisig args 0x{lock.args.hex()}")


def _templates(sheet: Sheet, groups) -> None:
    witnesses = sheet.transaction.witnesses
    for _, kind, inputs in groups.values():
        if kind is None:
            continue
        first = inputs[0]
        _refuse_unless(first < len(witnesses), "template.missing", f"input {first} has no witness")
        w = witnesses[first]
        if w == b"":
            continue
        try:
            args = decode_witness_args(w)
        except MoleculeError as e:
            raise Refused("template.form", f"witness {first} isn't a WitnessArgs: {e}") from e
        _refuse_unless(encode_witness_args(args) == w, "template.form", f"witness {first} doesn't re-encode to itself")
        _refuse_unless(args.lock is None, "template.form", f"witness {first} has a lock")
        ok = args.input_type is not None or args.output_type is not None
        _refuse_unless(ok, "template.form", f"witness {first} is an empty WitnessArgs, which is written 0x")


def _proofs(sheet: Sheet, spent) -> None:
    withdrawing = {
        i.previous_output.tx_hash
        for i, (output, data) in zip(sheet.transaction.raw.inputs, spent, strict=True)
        if dao.withdrawing_deposit_number(output, data) is not None
    }
    for h in sheet.inclusion_proofs:
        ok = h in withdrawing
        _refuse_unless(ok, "inclusion-proofs.target", f"proof 0x{h.hex()} is for no Nervos DAO withdrawing input")
    for h, proof in sheet.inclusion_proofs.items():
        ok = proof.block_hash in sheet.headers
        _refuse_unless(ok, "inclusion-proofs.header", f"proof 0x{h.hex()} names a block whose header isn't carried")
    for h, proof in sheet.inclusion_proofs.items():
        ok = verify_transaction_proof(h, proof, sheet.headers[proof.block_hash])
        _refuse_unless(ok, "inclusion-proofs.verify", f"proof 0x{h.hex()} doesn't verify against its header")


def check(sheet: Sheet, development_chain: bool = False) -> Accepted:
    """The checks after the canonical and schema checks, on a parsed file."""
    spent = _spent(sheet)
    _headers(sheet)
    raw_groups = _groups(spent, development_chain)
    _configs(sheet, spent, raw_groups)
    _templates(sheet, raw_groups)
    _proofs(sheet, spent)
    groups = {}
    for h, (lock, kind, inputs) in raw_groups.items():
        config = sheet.multisig_configs[lock.args[:20]] if kind in scripts.MULTISIG_KINDS else None
        groups[h] = Group(h, lock, kind, tuple(inputs), config)
    for h, entries in sheet.signatures.items():
        g = groups.get(h)
        if g is not None and g.kind is None:
            ok = len(entries) <= CARRIED_LIMIT
            _refuse_unless(ok, "signatures.carried-limit", f"{len(entries)} entries in carried group 0x{h.hex()}")
    return Accepted(sheet, groups, spent, unsigned_id(sheet), development_chain)
