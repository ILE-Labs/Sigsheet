"""Ready and finalize.

A multisig group is ready when its usable verified signers include the first R members and number at least M.
Finalize takes the first R members, then the lowest usable member positions, until it has M, and writes them in member
order after the multisig script: a lock of exactly 4 + 20N + 65M bytes
(https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c#L163-L189).
In a group of the genesis deployment, a position the genesis binary rejects isn't usable: position 10 when M <= 10,
and position 18 when M = 1 (measured for N up to 24, design record section 5.5). R <= M, so neither is ever a
required member. A single-key group is ready with its one signature, which is its 65-byte lock. When groups of carried
kinds are present, finalize is partial: it writes the groups version 1 signs and leaves every other witness as it is.
"""

from dataclasses import dataclass

from ..ckb import scripts
from ..ckb.molecule import Transaction
from .messages import first_witness
from .reader import Accepted, Group
from .signatures import Verified


class NotReady(Exception):
    pass


@dataclass(frozen=True, slots=True)
class GroupStatus:
    group: Group
    signed: tuple[int, ...]
    usable: tuple[int, ...]
    chosen: tuple[int, ...] | None

    @property
    def ready(self) -> bool:
        return self.chosen is not None


def genesis_skips(position: int, threshold: int) -> bool:
    return (position == 10 and threshold <= 10) or (position == 18 and threshold == 1)


def group_status(group: Group, verified: Verified) -> GroupStatus | None:
    """The status of a group version 1 signs; None for a carried group."""
    entries = verified.signatures.get(group.lock_hash, {})
    if group.kind is None:
        return None
    if group.kind == scripts.SINGLE_KEY:
        signed = (0,) if group.lock.args in entries else ()
        return GroupStatus(group, signed, signed, signed or None)
    keys = group.config.public_key_hashes
    signed = tuple(sorted(keys.index(k) for k in entries))
    usable = signed
    if group.kind == scripts.MULTISIG_GENESIS:
        usable = tuple(p for p in signed if not genesis_skips(p, group.config.threshold))
    r, m = group.config.require_first_n, group.config.threshold
    if not all(p in usable for p in range(r)) or len(usable) < m:
        return GroupStatus(group, signed, usable, None)
    chosen = tuple(range(r)) + tuple(p for p in usable if p >= r)[: m - r]
    return GroupStatus(group, signed, usable, chosen)


def status(accepted: Accepted, verified: Verified) -> dict[bytes, GroupStatus | None]:
    return {h: group_status(g, verified) for h, g in accepted.groups.items()}


def finalize(accepted: Accepted, verified: Verified) -> tuple[Transaction, bool]:
    """The final transaction, and whether it is partial (carried groups left as they are)."""
    tx = accepted.sheet.transaction
    witnesses = list(tx.witnesses)
    partial = False
    for h, st in status(accepted, verified).items():
        group = accepted.groups[h]
        if st is None:
            partial = True
            continue
        if not st.ready:
            raise NotReady(f"group 0x{h.hex()} isn't ready")
        entries = verified.signatures[h]
        if group.kind == scripts.SINGLE_KEY:
            lock = entries[group.lock.args]
        else:
            keys = group.config.public_key_hashes
            lock = group.config.script() + b"".join(entries[keys[p]] for p in st.chosen)
        first = group.inputs[0]
        witnesses[first] = first_witness(witnesses[first], lock)
    return Transaction(tx.raw, tuple(witnesses)), partial
