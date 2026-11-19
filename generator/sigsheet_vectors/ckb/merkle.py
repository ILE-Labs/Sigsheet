"""CKB Merkle Tree roots and transaction-proof verification.

The tree is a CBMT (RFC 0006,
https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0006-merkle-tree/0006-merkle-tree.md#L13-L155):
nodes are numbered top to bottom, left to right; with n items, item i is node i + n - 1; the parent of node i is
(i - 1) / 2 and its sibling ((i + 1) ^ 1) - 1; a left node has an odd number. A proof lists the node numbers of its
items and the lemmas, the hashes along the path that can't be computed, in descending node order.

A block's `transactions_root` is ckbhash(T || W), with T the CBMT root of its transaction hashes and W the root of
its witness hashes, and the CBMT merge is ckbhash(left || right) (RFC 0027,
https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0027-block-structure/0027-block-structure.md#L249-L263).
"""

from dataclasses import dataclass

from .hashing import ckbhash
from .molecule import Header, header_hash


@dataclass(frozen=True, slots=True)
class TransactionProof:
    """A node's `get_transaction_proof` result for one transaction."""

    block_hash: bytes
    indices: tuple[int, ...]
    lemmas: tuple[bytes, ...]
    witnesses_root: bytes


def merge(left: bytes, right: bytes) -> bytes:
    return ckbhash(left + right)


def cbmt_root(leaves: list[tuple[int, bytes]], lemmas: tuple[bytes, ...]) -> bytes | None:
    """The root RFC 0006's validation computes from (node number, hash) pairs and the lemmas, or None when the
    proof doesn't reach the root with every lemma used exactly once."""
    if not leaves:
        return None
    queue = sorted(leaves, key=lambda x: -x[0])
    if len(queue) == 1 and queue[0][0] == 0:
        return queue[0][1] if not lemmas else None
    used = 0
    while queue:
        index1, hash1 = queue.pop(0)
        if index1 == 0:
            return None
        sibling = ((index1 + 1) ^ 1) - 1
        if queue and queue[0][0] == sibling:
            _, hash2 = queue.pop(0)
            node = merge(hash2, hash1)
        else:
            if used == len(lemmas):
                return None
            hash2 = lemmas[used]
            used += 1
            node = merge(hash1, hash2) if index1 & 1 else merge(hash2, hash1)
        parent = (index1 - 1) // 2
        if parent == 0:
            return node if used == len(lemmas) and not queue else None
        queue.append((parent, node))
    return None


def verify_transaction_proof(tx_hash: bytes, proof: TransactionProof, header: Header) -> bool:
    """True when the proof shows the transaction in the block whose header is given."""
    if header_hash(header) != proof.block_hash or len(proof.indices) != 1:
        return False
    raw_root = cbmt_root([(proof.indices[0], tx_hash)], proof.lemmas)
    if raw_root is None:
        return False
    return merge(raw_root, proof.witnesses_root) == header.transactions_root
