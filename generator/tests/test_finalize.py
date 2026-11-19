"""Ready and finalize: the genesis rule against the measured sets (XRT-1, XRTb-1), first R, partial finalize."""

import pathlib
import unittest

from sigsheet_vectors.ckb import molecule, rpc_json, scripts
from sigsheet_vectors.sigsheet import canonical, finalize, reader, signatures
from sigsheet_vectors.sigsheet.finalize import genesis_skips

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


def state(case: str):
    data = (ROOT / "cases" / case / "merged.json").read_bytes()
    accepted = reader.read(data, development_chain=True)
    return accepted, signatures.verify(accepted)


class GenesisRuleTest(unittest.TestCase):
    def test_the_skipped_positions(self):
        # A genesis set fails when position 10 signs with M <= 10, or position 18 with M = 1 (N up to 24).
        self.assertTrue(genesis_skips(10, 2))
        self.assertTrue(genesis_skips(10, 10))
        self.assertFalse(genesis_skips(10, 11))
        self.assertTrue(genesis_skips(18, 1))
        self.assertFalse(genesis_skips(18, 2))
        self.assertFalse(any(genesis_skips(p, m) for p in range(25) for m in range(1, 25) if p not in (10, 18)))

    def test_the_vectors(self):
        cases = {
            "genesis-n12-m2-skip-10": (5, 11),
            "genesis-n12-m11-r11": tuple(range(11)),
            "genesis-n12-m2-10-11-not-ready": None,
            "genesis-n20-m1-18-not-ready": None,
        }
        for case, chosen in cases.items():
            accepted, v = state(case)
            (st,) = finalize.status(accepted, v).values()
            self.assertEqual(st.chosen, chosen, case)

    def test_a_required_member_is_never_skipped(self):
        for m in range(1, 25):
            for r in range(m + 1):
                self.assertFalse(any(genesis_skips(p, m) for p in range(r)))

    def test_other_deployments_skip_nothing(self):
        accepted, v = state("S3-v2-2of3-two-inputs")
        (st,) = finalize.status(accepted, v).values()
        self.assertEqual(st.usable, st.signed)


class FinalizeTest(unittest.TestCase):
    def test_first_r_is_required(self):
        accepted, v = state("S4N-v2-first-R-missing-required")
        (st,) = finalize.status(accepted, v).values()
        self.assertFalse(st.ready)
        with self.assertRaises(finalize.NotReady):
            finalize.finalize(accepted, v)

    def test_the_lock_is_exactly_4_plus_20n_plus_65m_bytes_in_member_order(self):
        accepted, v = state("R1-35-first-member-required")
        tx, partial = finalize.finalize(accepted, v)
        self.assertFalse(partial)
        (group,) = accepted.groups.values()
        c = group.config
        lock = molecule.decode_witness_args(tx.witnesses[group.inputs[0]]).lock
        self.assertEqual(len(lock), 4 + 20 * len(c.public_key_hashes) + 65 * c.threshold)
        (st,) = finalize.status(accepted, v).values()
        self.assertEqual(st.chosen, (0, 1, 2))

    def test_partial_finalize_leaves_carried_witnesses(self):
        for case in ("unknown-lock-partial", "omnilock-multisig-carried"):
            accepted, v = state(case)
            tx, partial = finalize.finalize(accepted, v)
            self.assertTrue(partial)
            for g in accepted.groups.values():
                w = tx.witnesses[g.inputs[0]]
                self.assertEqual(w == accepted.sheet.transaction.witnesses[g.inputs[0]], g.kind is None, case)

    def test_final_transactions_equal_the_committed_ones(self):
        for folder in sorted(ROOT.glob("cases/*")):
            committed = canonical.check((folder / "input.json").read_bytes()).get("recorded", {}).get("committed")
            if committed and "witnesses" in committed:
                final = canonical.check((folder / "final-tx.json").read_bytes())
                self.assertEqual(final["witnesses"], committed["witnesses"], folder.name)
                tx = rpc_json.transaction_from(final, "final")
                self.assertEqual(rpc_json.fmt_bytes(molecule.transaction_hash(tx.raw)), committed["hash"])

    def test_a_single_key_group_is_ready_with_its_signature(self):
        accepted, v = state("S7-multisig-plus-single-key")
        sts = finalize.status(accepted, v)
        single = next(s for s in sts.values() if s and s.group.kind == scripts.SINGLE_KEY)
        self.assertTrue(single.ready)


if __name__ == "__main__":
    unittest.main()
