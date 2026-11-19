"""Each group's message, computed from the file alone, equals the one recorded by the experiments (X1)."""

import pathlib
import unittest

from sigsheet_vectors.ckb.rpc_json import fmt_bytes
from sigsheet_vectors.sigsheet import canonical, reader
from sigsheet_vectors.sigsheet.messages import message

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"
RECORDED = (
    "S1-genesis-2of3",
    "S2-2024-2of3",
    "S3-v2-2of3-two-inputs",
    "S4-v2-first-R",
    "S4N-v2-first-R-missing-required",
    "S5-v2-since-in-args",
    "S6-two-multisig-groups",
    "S7-multisig-plus-single-key",
    "S8-neuron-export",
    "S9-extra-witness",
)


class MessagesTest(unittest.TestCase):
    def test_x1s_messages(self):
        n = 0
        for case in RECORDED:
            recorded = canonical.check((ROOT / "cases" / case / "input.json").read_bytes())["recorded"]["messages"]
            accepted = reader.read((ROOT / "cases" / case / "file.json").read_bytes(), development_chain=True)
            for group, msg in recorded.items():
                g = accepted.groups[bytes.fromhex(group[2:])]
                self.assertEqual(fmt_bytes(message(accepted, g)), msg, case)
                n += 1
        self.assertEqual(n, 12)

    def test_signatures_dont_change_the_message(self):
        a = reader.read((ROOT / "cases/S6-two-multisig-groups/file.json").read_bytes(), True)
        b = reader.read((ROOT / "cases/S6-two-multisig-groups/merged.json").read_bytes(), True)
        for h, g in a.groups.items():
            self.assertEqual(message(a, g), message(b, b.groups[h]))

    def test_no_message_for_a_carried_lock(self):
        a = reader.read((ROOT / "cases/unknown-lock-partial/file.json").read_bytes())
        carried = next(g for g in a.groups.values() if g.kind is None)
        with self.assertRaises(ValueError):
            message(a, carried)


if __name__ == "__main__":
    unittest.main()
