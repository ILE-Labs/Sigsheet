"""Verifying the signatures of an accepted file, keyed by lock group and signer.

For a group of a kind version 1 signs, each entry is checked in this order: the filed signer must be a member (for
the single-key lock, the args' key), before any key recovery; the 65 bytes must recover a key over the group's
message; that key's blake160 must be the filed signer. A failing entry is dropped with its reason id. A passing one is
kept in low-s form: the locks also accept the high-s twin of a signature, so one member can have two valid byte
strings, and normalizing makes every reader keep the same one. Entries in a group of a kind the reader carries are
kept unchanged and unverified. Entries under a lock hash that is no group of the transaction are dropped.
"""

from dataclasses import dataclass

from ..ckb import scripts
from ..ckb.hashing import blake160
from ..ckb.secp256k1 import InvalidSignature, normalize_low_s, recover
from .messages import message
from .reader import Accepted, Group


@dataclass(frozen=True, slots=True)
class Drop:
    group: bytes
    signer: bytes
    reason: str


@dataclass(frozen=True, slots=True)
class Verified:
    signatures: dict[bytes, dict[bytes, bytes]]
    carried: dict[bytes, dict[bytes, bytes]]
    dropped: tuple[Drop, ...]
    normalized: tuple[tuple[bytes, bytes], ...]


def members(group: Group) -> tuple[bytes, ...]:
    if group.kind == scripts.SINGLE_KEY:
        return (group.lock.args,)
    return group.config.public_key_hashes


def check_entry(group: Group, msg: bytes, signer: bytes, signature: bytes) -> str | None:
    """The drop reason for one entry of a group version 1 signs, or None when it verifies."""
    if signer not in members(group):
        return "drop.not-member"
    try:
        key = recover(msg, signature)
    except InvalidSignature:
        return "drop.invalid"
    return None if blake160(key) == signer else "drop.mismatch"


def verify(accepted: Accepted) -> Verified:
    verified: dict[bytes, dict[bytes, bytes]] = {}
    carried: dict[bytes, dict[bytes, bytes]] = {}
    dropped: list[Drop] = []
    normalized: list[tuple[bytes, bytes]] = []
    for gh in sorted(accepted.sheet.signatures):
        entries = accepted.sheet.signatures[gh]
        group = accepted.groups.get(gh)
        if group is None:
            dropped += [Drop(gh, signer, "drop.no-group") for signer in sorted(entries)]
            continue
        if group.kind is None:
            carried[gh] = dict(entries)
            continue
        msg = message(accepted, group)
        for signer in sorted(entries):
            sig = entries[signer]
            reason = check_entry(group, msg, signer, sig)
            if reason:
                dropped.append(Drop(gh, signer, reason))
                continue
            low = normalize_low_s(sig)
            if low != sig:
                normalized.append((gh, signer))
            verified.setdefault(gh, {})[signer] = low
    return Verified(verified, carried, tuple(dropped), tuple(normalized))
