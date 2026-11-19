"""The case list matches vectors/cases/, and every case reproduces its recorded results."""

import pathlib
import unittest

from sigsheet_vectors.sigsheet import canonical
from sigsheet_vectors.vectors import cases

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


class CasesTest(unittest.TestCase):
    def test_the_list_matches_the_folders(self):
        ids = [c.id for c in cases.CASES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids), sorted(p.name for p in (ROOT / "cases").iterdir()))

    def test_every_case_builds_as_on_disk(self):
        for c in cases.CASES:
            folder = ROOT / "cases" / c.id
            files = cases.build(c.id, (folder / "input.json").read_bytes(), c.expect)
            for name, data in files.items():
                self.assertEqual((folder / name).read_bytes(), data, f"{c.id}/{name}")

    def test_a_result_that_differs_from_the_recording_stops_the_build(self):
        inp = canonical.check((ROOT / "cases/S1-genesis-2of3/input.json").read_bytes())
        group = next(iter(inp["recorded"]["messages"]))
        inp["recorded"]["messages"][group] = "0x" + "00" * 32
        with self.assertRaises(cases.VectorMismatch):
            cases.build("S1-genesis-2of3", canonical.encode(inp))
        with self.assertRaises(cases.VectorMismatch):
            cases.build("dao-proof-block-changed", (ROOT / "cases/dao-proof-block-changed/input.json").read_bytes())


if __name__ == "__main__":
    unittest.main()
