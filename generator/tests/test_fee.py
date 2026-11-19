"""The fee: exact from inclusion proofs, an upper bound without them, never lowered (XRTb-3's figures)."""

import pathlib
import unittest

from sigsheet_vectors.sigsheet import fee, reader

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


def fee_of(case: str, name: str = "merged.json") -> fee.Fee:
    return fee.fee(reader.read((ROOT / "cases" / case / name).read_bytes(), development_chain=True))


class FeeTest(unittest.TestCase):
    def test_with_proofs_the_fee_is_the_nodes(self):
        f = fee_of("dao-two-deposits")
        self.assertEqual((f.kind, f.shannons), ("exact", 100_000))
        self.assertEqual([d.amount for d in f.dao_inputs], [200_002_791_696, 300_709_831_092])

    def test_without_proofs_an_upper_bound(self):
        f = fee_of("dao-two-deposits-no-proofs")
        self.assertEqual((f.kind, f.shannons), ("at most", 463_600_414))
        self.assertGreaterEqual(f.shannons, fee_of("dao-two-deposits").shannons)

    def test_the_cut_output_shows_the_real_fee(self):
        f = fee_of("dao-cut-output", "file.json")
        self.assertEqual((f.kind, f.shannons), ("exact", 712_722_788))

    def test_without_a_dao_input_inputs_minus_outputs(self):
        f = fee_of("S1-genesis-2of3")
        self.assertEqual((f.kind, f.shannons, f.dao_inputs), ("exact", 100_000, ()))


if __name__ == "__main__":
    unittest.main()
