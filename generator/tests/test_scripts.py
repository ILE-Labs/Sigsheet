"""Lock kinds, tokens and the network, from code hashes and cell deps."""

import unittest

from sigsheet_vectors.ckb import scripts
from sigsheet_vectors.ckb.molecule import CellDep, OutPoint, Script


class ScriptsTest(unittest.TestCase):
    def test_lock_kinds(self):
        self.assertEqual(scripts.lock_kind(Script(scripts.SINGLE_KEY_CODE_HASH, "type", bytes(20))), scripts.SINGLE_KEY)
        self.assertEqual(
            scripts.lock_kind(Script(scripts.GENESIS_CODE_HASH, "type", bytes(20))), scripts.MULTISIG_GENESIS
        )
        self.assertEqual(scripts.lock_kind(Script(scripts.V2_CODE_HASH, "data1", bytes(20))), scripts.MULTISIG_V2)
        self.assertIsNone(scripts.lock_kind(Script(scripts.V2_CODE_HASH, "type", bytes(20))))
        self.assertIsNone(scripts.lock_kind(Script(scripts.V2_CODE_HASH, "data", bytes(20))))
        for (code_hash, hash_type), kind in scripts.LOCK_KINDS.items():
            self.assertEqual(scripts.lock_kind(Script(code_hash, hash_type, b"")), kind)

    def test_the_development_chain_hash_only_when_asked(self):
        ((code_hash, hash_type),) = scripts.DEVELOPMENT_CHAIN_LOCK_KINDS
        lock = Script(code_hash, hash_type, bytes(20))
        self.assertIsNone(scripts.lock_kind(lock))
        self.assertEqual(scripts.lock_kind(lock, development_chain=True), scripts.MULTISIG_2024)

    def test_tokens(self):
        self.assertIsNone(scripts.token_kind(None))
        for (code_hash, hash_type), kind in scripts.TOKENS.items():
            self.assertEqual(scripts.token_kind(Script(code_hash, hash_type, bytes(32))), kind)

    def test_network(self):
        main = next(iter(scripts.KNOWN_CELL_DEPS["mainnet"]))
        test = next(iter(scripts.KNOWN_CELL_DEPS["testnet"]))
        other = CellDep(OutPoint(bytes(32), 0), "dep_group")
        self.assertEqual(scripts.network((main, other)), "mainnet")
        self.assertEqual(scripts.network((test,)), "testnet")
        self.assertEqual(scripts.network((main, test)), "unknown")
        self.assertEqual(scripts.network((other,)), "unknown")
        self.assertEqual(scripts.network(()), "unknown")


if __name__ == "__main__":
    unittest.main()
