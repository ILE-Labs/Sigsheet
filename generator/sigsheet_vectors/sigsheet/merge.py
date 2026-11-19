"""Merging copies of one file, in any order and any grouping, to the same bytes.

Only files the reader accepts are merged, and only when they have the same unsigned id. Their context and headers
are then equal: each file holds exactly the entries its transaction needs. The result keeps every verified member
signature in low-s form, the smaller bytes when one signer has two, and signatures beyond M; inclusion proofs and
configs are united (each is keyed by a hash of its content); entries of carried kinds are kept unchanged, and two
different entries under one signer in such a group refuse the merge, since no reader of that version can tell which
is valid. Dropped entries don't reach the result.
"""

from ..ckb.rpc_json import proof_to
from . import canonical
from .reader import Refused, read
from .schema import Sheet, to_json
from .signatures import verify


class MergeRefused(Exception):
    def __init__(self, check_id: str, detail: str):
        super().__init__(f"{check_id}: {detail}")
        self.check_id = check_id
        self.detail = detail


def merge(files: list[bytes], development_chain: bool = False) -> bytes:
    if not files:
        raise ValueError("nothing to merge")
    accepted = []
    for n, data in enumerate(files):
        try:
            accepted.append(read(data, development_chain))
        except Refused as e:
            raise MergeRefused(e.check_id, f"file {n} is refused: {e.detail}") from e
    uid = accepted[0].unsigned_id
    if any(a.unsigned_id != uid for a in accepted):
        raise MergeRefused("merge.unsigned-id", "the files describe different unsigned transactions")
    proofs, configs = {}, {}
    for a in accepted:
        for h, p in a.sheet.inclusion_proofs.items():
            cur = proofs.get(h)
            if cur is None or _proof_bytes(p) < _proof_bytes(cur):
                proofs[h] = p
        configs.update(a.sheet.multisig_configs)
    signatures: dict[bytes, dict[bytes, bytes]] = {}
    for a in accepted:
        v = verify(a)
        for gh, entries in v.signatures.items():
            for signer, sig in entries.items():
                cur = signatures.setdefault(gh, {}).get(signer)
                if cur is None or sig < cur:
                    signatures[gh][signer] = sig
        for gh, entries in v.carried.items():
            for signer, sig in entries.items():
                cur = signatures.setdefault(gh, {}).get(signer)
                if cur is not None and cur != sig:
                    raise MergeRefused(
                        "merge.carried-conflict", f"two entries for signer 0x{signer.hex()} in a carried group"
                    )
                signatures[gh][signer] = sig
    base = accepted[0].sheet
    merged = Sheet(base.transaction, base.context, base.headers, proofs, configs, signatures)
    out = canonical.encode(to_json(merged))
    read(out, development_chain)
    return out


def _proof_bytes(p) -> bytes:
    return canonical.encode(proof_to(p))
