"""Verification: membership first, then recovery; each drop reason; low-s; carried entries kept."""

import copy
import pathlib
import unittest

from sigsheet_vectors.ckb.secp256k1 import high_s_twin
from sigsheet_vectors.sigsheet import canonical, reader, signatures

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


def verify(v: dict) -> signatures.Verified:
    return signatures.verify(reader.read(canonical.encode(v), True))


class SignaturesTest(unittest.TestCase):
    def setUp(self):
        self.v = canonical.check((ROOT / "cases/S1-genesis-2of3/merged.json").read_bytes())
        (self.group,) = self.v["signatures"]
        self.entries = self.v["signatures"][self.group]
        self.members = next(iter(self.v["multisig_configs"].values()))["public_key_hashes"]

    def test_the_recorded_signatures_verify(self):
        out = verify(self.v)
        self.assertEqual(len(out.signatures[bytes.fromhex(self.group[2:])]), 2)
        self.assertEqual(out.dropped, ())

    def test_each_drop_reason(self):
        v = copy.deepcopy(self.v)
        sig = next(iter(self.entries.values()))
        unsigned = next(m for m in self.members if m not in self.entries)
        v["signatures"]["0x" + "ab" * 32] = {self.members[0]: sig}
        v["signatures"][self.group]["0x" + "cd" * 20] = sig
        v["signatures"][self.group][unsigned] = "0x" + "00" * 65
        out = verify(v)
        reasons = sorted((d.reason, d.signer.hex()) for d in out.dropped)
        self.assertEqual([r for r, _ in reasons], ["drop.invalid", "drop.no-group", "drop.not-member"])
        v = copy.deepcopy(self.v)
        v["signatures"][self.group][unsigned] = sig
        self.assertEqual([d.reason for d in verify(v).dropped], ["drop.mismatch"])

    def test_membership_is_checked_before_recovery(self):
        v = copy.deepcopy(self.v)
        v["signatures"][self.group]["0x" + "cd" * 20] = "0x" + "00" * 65
        self.assertEqual([d.reason for d in verify(v).dropped], ["drop.not-member"])

    def test_a_high_s_twin_is_kept_in_low_s_form(self):
        v = copy.deepcopy(self.v)
        signer, sig = next(iter(self.entries.items()))
        v["signatures"][self.group][signer] = "0x" + high_s_twin(bytes.fromhex(sig[2:])).hex()
        out = verify(v)
        self.assertEqual(out.signatures[bytes.fromhex(self.group[2:])][bytes.fromhex(signer[2:])].hex(), sig[2:])
        self.assertEqual(len(out.normalized), 1)

    def test_carried_entries_are_kept_unverified(self):
        v = canonical.check((ROOT / "cases/unknown-lock-partial/merged.json").read_bytes())
        out = verify(v)
        self.assertEqual(len(out.carried), 1)
        self.assertEqual(out.dropped, ())


if __name__ == "__main__":
    unittest.main()
