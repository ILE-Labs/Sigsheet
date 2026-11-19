"""The attack list matches vectors/attacks/, each change does what it says, and a wrong declaration stops the build."""

import dataclasses
import pathlib
import unittest

from sigsheet_vectors.sigsheet import canonical
from sigsheet_vectors.vectors import attacks, cases

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


def bases():
    built, chains = {}, {}
    for c in cases.CASES:
        data = (ROOT / "cases" / c.id / "input.json").read_bytes()
        built[c.id] = cases.build(c.id, data, c.expect)
        chains[c.id] = canonical.check(data)["chain"]
    return built, chains


class AttacksTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.built, cls.chains = bases()

    def test_the_list_matches_the_folders(self):
        ids = [a.id for a in attacks.ATTACKS]
        self.assertEqual(sorted(ids), sorted(p.name for p in (ROOT / "attacks").iterdir()))

    def test_each_attack_builds_as_on_disk(self):
        for a in attacks.ATTACKS:
            folder = ROOT / "attacks" / a.id
            files = attacks.build(a, (folder / "input.json").read_bytes(), self.built, self.chains)
            for name, data in files.items():
                self.assertEqual((folder / name).read_bytes(), data, f"{a.id}/{name}")

    def test_a_wrong_declaration_stops_the_build(self):
        a = next(x for x in attacks.ATTACKS if x.id == "falsified-input-cell")
        data = (ROOT / "attacks" / a.id / "input.json").read_bytes()
        with self.assertRaises(cases.VectorMismatch):
            attacks.build(dataclasses.replace(a, outcome="context.missing"), data, self.built, self.chains)

    def test_changes(self):
        base = {
            "transaction": {
                "inputs": [{"since": "0x0", "previous_output": {"tx_hash": "0xaa", "index": "0x0"}}],
                "outputs": [{"capacity": "0x10"}],
                "witnesses": ["0x"],
            },
            "context": {"0xaa": {"outputs": [{"capacity": "0x5"}]}},
            "signatures": {},
            "multisig_configs": {},
        }
        v = attacks.apply(base, {"kind": "raise-input-capacity", "input": 0, "add": "0x1"})
        self.assertEqual(v["context"]["0xaa"]["outputs"][0]["capacity"], "0x6")
        self.assertEqual(base["context"]["0xaa"]["outputs"][0]["capacity"], "0x5")
        v = attacks.apply(base, {"kind": "lower-output-capacity", "output": 0, "by": "0x1"})
        self.assertEqual(v["transaction"]["outputs"][0]["capacity"], "0xf")
        v = attacks.apply(base, {"kind": "duplicate-input", "input": 0})
        self.assertEqual(len(v["transaction"]["inputs"]), 2)
        self.assertEqual(v["transaction"]["witnesses"], ["0x", "0x"])
        with self.assertRaises(ValueError):
            attacks.apply(base, {"kind": "unknown"})


if __name__ == "__main__":
    unittest.main()
