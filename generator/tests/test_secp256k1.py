"""Recovery, low-s and the high-s twin, on recorded signatures."""

import json
import pathlib
import secrets
import unittest

from sigsheet_vectors.ckb import secp256k1
from sigsheet_vectors.ckb.hashing import blake160

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        inp = json.loads((ROOT / "cases/S1-genesis-2of3/input.json").read_bytes())
        (self.message,) = (bytes.fromhex(m[2:]) for m in inp["recorded"]["messages"].values())
        self.entries = [(bytes.fromhex(e["signer"][2:]), bytes.fromhex(e["signature"][2:])) for e in inp["signatures"]]

    def test_recorded_signatures_recover_to_their_signers(self):
        for signer, sig in self.entries:
            self.assertEqual(blake160(secp256k1.recover(self.message, sig)), signer)
            self.assertTrue(secp256k1.is_low_s(sig))

    def test_the_high_s_twin_recovers_the_same_key(self):
        for _, sig in self.entries:
            twin = secp256k1.high_s_twin(sig)
            self.assertFalse(secp256k1.is_low_s(twin))
            self.assertEqual(secp256k1.recover(self.message, twin), secp256k1.recover(self.message, sig))
            self.assertEqual(secp256k1.normalize_low_s(twin), sig)

    def test_out_of_range_signatures_are_invalid(self):
        _, sig = self.entries[0]
        n = secp256k1.N.to_bytes(32, "big")
        for bad in (
            bytes(32) + sig[32:],
            sig[:32] + bytes(32) + sig[64:],
            n + sig[32:],
            sig[:32] + n + sig[64:],
            sig[:64] + b"\x04",
        ):
            with self.assertRaises(secp256k1.InvalidSignature):
                secp256k1.recover(self.message, bad)

    def test_constants(self):
        self.assertEqual(secp256k1.HALF_N, secp256k1.N // 2)
        x, y = secp256k1.GX, secp256k1.GY
        self.assertEqual((y * y - x * x * x - secp256k1.CURVE_B) % secp256k1.P, 0)

    def test_sign_then_recover(self):
        secret = secrets.token_bytes(32)
        sig = secp256k1.sign(self.message, secret)
        self.assertTrue(secp256k1.is_low_s(sig))
        self.assertEqual(secp256k1.recover(self.message, sig), secp256k1.public_key(secret))


if __name__ == "__main__":
    unittest.main()
