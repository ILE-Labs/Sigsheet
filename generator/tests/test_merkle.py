"""CBMT roots and transaction proofs: the recorded devnet proofs, and trees built as RFC 0006 lays them out."""

import json
import pathlib
import unittest

from sigsheet_vectors.ckb import merkle, rpc_json
from sigsheet_vectors.ckb.hashing import ckbhash

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


def tree(leaves: list[bytes]) -> list[bytes]:
    """RFC 0006's array: 2n - 1 nodes, item i at i + n - 1, each inner node the merge of its children."""
    n = len(leaves)
    nodes = [b""] * (n - 1) + leaves
    for i in range(n - 2, -1, -1):
        nodes[i] = merkle.merge(nodes[2 * i + 1], nodes[2 * i + 2])
    return nodes


def proof_for(nodes: list[bytes], i: int, n: int) -> tuple[int, tuple[bytes, ...]]:
    node, lemmas = i + n - 1, []
    while node:
        lemmas.append(nodes[((node + 1) ^ 1) - 1])
        node = (node - 1) // 2
    return i + n - 1, tuple(lemmas)


class CbmtTest(unittest.TestCase):
    def test_every_leaf_of_trees_of_1_to_9_items(self):
        for n in range(1, 10):
            leaves = [ckbhash(bytes([n, i])) for i in range(n)]
            nodes = tree(leaves)
            for i in range(n):
                index, lemmas = proof_for(nodes, i, n)
                self.assertEqual(merkle.cbmt_root([(index, leaves[i])], lemmas), nodes[0])
                if lemmas:
                    self.assertIsNone(merkle.cbmt_root([(index, leaves[i])], lemmas[:-1]))
                    self.assertIsNone(merkle.cbmt_root([(index, leaves[i])], (*lemmas, leaves[0])))


class TransactionProofTest(unittest.TestCase):
    def setUp(self):
        node = json.loads((ROOT / "cases/dao-two-deposits/input.json").read_bytes())["node"]
        self.headers = {h: rpc_json.header_view_from(v, h) for h, v in node["get_header"].items()}
        self.proofs = {h: rpc_json.proof_from(p, h) for h, p in node["get_transaction_proof"].items()}

    def test_the_recorded_proofs_verify(self):
        for h, p in self.proofs.items():
            header = self.headers[rpc_json.fmt_bytes(p.block_hash)]
            self.assertTrue(merkle.verify_transaction_proof(bytes.fromhex(h[2:]), p, header))

    def test_a_proof_naming_another_block_fails(self):
        for h, p in self.proofs.items():
            for other_hash, other in self.headers.items():
                if bytes.fromhex(other_hash[2:]) != p.block_hash:
                    forged = merkle.TransactionProof(
                        bytes.fromhex(other_hash[2:]), p.indices, p.lemmas, p.witnesses_root
                    )
                    self.assertFalse(merkle.verify_transaction_proof(bytes.fromhex(h[2:]), forged, other))

    def test_a_proof_checked_against_another_transaction_fails(self):
        (h1, p1), (h2, _) = self.proofs.items()
        header = self.headers[rpc_json.fmt_bytes(p1.block_hash)]
        self.assertFalse(merkle.verify_transaction_proof(bytes.fromhex(h2[2:]), p1, header))


if __name__ == "__main__":
    unittest.main()
