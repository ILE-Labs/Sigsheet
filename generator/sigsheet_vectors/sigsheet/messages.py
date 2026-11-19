"""The signing message of each lock kind version 1 signs, computed from the file alone.

All four kinds use the rule of the system locks at ckb-system-scripts 72eb92f: ckbhash over the transaction hash;
the group's first witness with its lock replaced by zeros, preceded by its length as a u64 (little-endian); each other
witness of the group, each preceded by its length, stopping at the first group input that has no witness; then every
witness at an index at or beyond the number of inputs, each preceded by its length
(https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c#L205-L281).
The zeroed lock is the multisig script followed by M * 65 zero bytes for a multisig group, and 65 zero bytes for the
single-key lock
(https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_sighash_all.c#L154-L215).
The genesis, 2024 and v2 deployments share the rule.
"""

from ..ckb import scripts
from ..ckb.hashing import hasher
from ..ckb.molecule import WitnessArgs, decode_witness_args, encode_witness_args, transaction_hash, uint
from .reader import Accepted, Group

SIGNATURE_SIZE = 65


def zeroed_lock(group: Group) -> bytes:
    if group.kind == scripts.SINGLE_KEY:
        return bytes(SIGNATURE_SIZE)
    return group.config.script() + bytes(SIGNATURE_SIZE * group.config.threshold)


def first_witness(template: bytes, lock: bytes) -> bytes:
    """The group's first witness with `lock` in place: the template's input_type and output_type are kept."""
    args = decode_witness_args(template) if template else WitnessArgs()
    return encode_witness_args(WitnessArgs(lock, args.input_type, args.output_type))


def message(accepted: Accepted, group: Group) -> bytes:
    if group.kind is None:
        raise ValueError("no message rule for a lock version 1 carries")
    tx = accepted.sheet.transaction
    witnesses = tx.witnesses
    first = first_witness(witnesses[group.inputs[0]], zeroed_lock(group))
    h = hasher()
    h.update(transaction_hash(tx.raw))
    h.update(uint(len(first), 8) + first)
    for i in group.inputs[1:]:
        if i >= len(witnesses):
            break
        h.update(uint(len(witnesses[i]), 8) + witnesses[i])
    for w in witnesses[len(tx.raw.inputs) :]:
        h.update(uint(len(w), 8) + w)
    return h.digest()
