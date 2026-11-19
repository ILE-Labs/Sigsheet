"""What a signer is shown: tokens and the type warning, labels, the since rule, the network."""

import pathlib
import unittest

from sigsheet_vectors.sigsheet import canonical, reader, show, signatures

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


def view(path: str) -> dict:
    accepted = reader.read((ROOT / path).read_bytes(), development_chain=True)
    return show.view(accepted, signatures.verify(accepted))


class ShowTest(unittest.TestCase):
    def test_a_token_that_leaves(self):
        v = view("attacks/token-consumed/attack.json")
        self.assertEqual(v["inputs"][1]["token"]["kind"], "xUDT")
        self.assertEqual(v["inputs"][1]["token"]["amount"], "1000000")
        (warning,) = v["warnings"]
        self.assertEqual((warning["id"], warning["input"], warning["token"]["amount"]), ("type-leaves", 1, "1000000"))
        self.assertEqual(v["tokens"][0]["in"], "1000000")
        self.assertEqual(v["tokens"][0]["out"], "0")
        self.assertEqual(v["outputs"][0]["label"], "back to the lock of input 0")
        self.assertEqual(v["fee"]["shannons"], "100000")

    def test_labels(self):
        v = view("cases/S1-genesis-2of3/merged.json")
        self.assertEqual([o["label"] for o in v["outputs"]], ["payment", "back to the lock of input 0"])

    def test_the_since_rule_by_deployment(self):
        self.assertIn(
            "since-rejected", [w["id"] for w in view("attacks/since-rejected-by-lock/attack.json")["warnings"]]
        )
        self.assertEqual(view("cases/S5-v2-since-in-args/merged.json")["warnings"], [])
        self.assertFalse(show.since_accepted(0, 0x8000000000000001))
        self.assertTrue(show.since_accepted(0, 5))
        epoch = 0x20 << 56
        self.assertTrue(show.since_accepted(epoch | 10 | (1 << 24) | (2 << 40), epoch | 10 | (2 << 24) | (4 << 40)))
        self.assertFalse(show.since_accepted(epoch | 10 | (2 << 24) | (4 << 40), epoch | 10 | (1 << 24) | (3 << 40)))

    def test_an_unknown_network_shows_both_address_forms(self):
        v = view("cases/S1-genesis-2of3/merged.json")
        self.assertEqual(v["network"], "unknown")
        self.assertEqual(sorted(v["inputs"][0]["lock"]["addresses"]), ["mainnet", "testnet"])
        v = view("cases/genesis-n12-m2-skip-10/merged.json")
        self.assertEqual(v["network"], "mainnet")
        self.assertEqual(sorted(v["inputs"][0]["lock"]["addresses"]), ["mainnet"])

    def test_the_view_is_in_the_canonical_domain(self):
        for path in sorted(ROOT.glob("cases/*/merged.json")):
            if (path.parent / "expected.json").exists():
                expected = canonical.check((path.parent / "expected.json").read_bytes())
                if expected["outcome"] == "accepted":
                    self.assertEqual(expected["shown"], view(str(path.relative_to(ROOT))))


if __name__ == "__main__":
    unittest.main()
