"""ckbhash and blake160.

ckbhash is BLAKE2b with a 32-byte digest and the personalization "ckb-default-hash"; blake160 is its first
20 bytes (RFC 0022, https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0022-transaction-structure/0022-transaction-structure.md#L385-L388).
"""

import hashlib

PERSONALIZATION = b"ckb-default-hash"


def hasher():
    """An incremental ckbhash."""
    return hashlib.blake2b(digest_size=32, person=PERSONALIZATION)


def ckbhash(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=32, person=PERSONALIZATION).digest()


def blake160(data: bytes) -> bytes:
    return ckbhash(data)[:20]
