"""Full-format addresses against RFC 0021's own test vector."""

import unittest

from sigsheet_vectors.ckb import addresses
from sigsheet_vectors.ckb.molecule import Script

# RFC 0021 L115-L119 (https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0021-ckb-address-format/0021-ckb-address-format.md#L115-L119).
SCRIPT = Script(
    bytes.fromhex("9bd7e06f3ecf4be0f2fcd2188b23f1b9fcc88e5d4b65a8637b17723bbda3cce8"),
    "type",
    bytes.fromhex("b39bbc0b3673c7d36450bc14cfcdad2d559c6c64"),
)
ADDRESS = "ckb1qzda0cr08m85hc8jlnfp3zer7xulejywt49kt2rr0vthywaa50xwsqdnnw7qkdnnclfkg59uzn8umtfd2kwxceqxwquc4"


class AddressesTest(unittest.TestCase):
    def test_rfc_vector(self):
        self.assertEqual(addresses.encode(SCRIPT, "mainnet"), ADDRESS)
        self.assertEqual(addresses.decode(ADDRESS), ("mainnet", SCRIPT))

    def test_testnet_prefix_and_round_trip(self):
        a = addresses.encode(SCRIPT, "testnet")
        self.assertTrue(a.startswith("ckt1"))
        self.assertEqual(addresses.decode(a), ("testnet", SCRIPT))

    def test_a_changed_character_is_refused(self):
        bad = ADDRESS[:-1] + ("q" if ADDRESS[-1] != "q" else "p")
        with self.assertRaises(ValueError):
            addresses.decode(bad)
        with self.assertRaises(ValueError):
            addresses.decode(ADDRESS.upper())


if __name__ == "__main__":
    unittest.main()
