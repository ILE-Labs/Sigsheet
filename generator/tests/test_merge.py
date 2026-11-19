"""Merge: one byte string from every vector's partial files in 200 random orders and groupings; the refusals."""

import pathlib
import random
import unittest

from sigsheet_vectors.sigsheet import canonical, merge

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"
TRIALS = 200
SEED = 20261119


def vectors():
    for folder in sorted(ROOT.glob("cases/*")):
        partials = [p.read_bytes() for p in sorted((folder / "partial").glob("*.json"))]
        if partials:
            chain = canonical.check((folder / "input.json").read_bytes())["chain"]
            yield folder.name, partials, (folder / "merged.json").read_bytes(), chain == "devnet"


class MergeTest(unittest.TestCase):
    def test_any_order_and_grouping_gives_the_merged_file(self):
        rng = random.Random(SEED)
        count = 0
        for name, partials, merged, dev in vectors():
            for _ in range(TRIALS):
                files = partials[:]
                rng.shuffle(files)
                cut = sorted(rng.sample(range(1, len(files)), rng.randrange(len(files)))) if len(files) > 1 else []
                groups = [files[a:b] for a, b in zip([0, *cut], [*cut, len(files)], strict=True)]
                parts = [merge.merge(g, dev) for g in groups]
                rng.shuffle(parts)
                self.assertEqual(merge.merge(parts, dev), merged, name)
            count += 1
        self.assertGreaterEqual(count, 20)

    def test_merge_is_idempotent(self):
        for name, _, merged, dev in vectors():
            self.assertEqual(merge.merge([merged, merged], dev), merged, name)

    def test_different_unsigned_ids_are_refused(self):
        a = (ROOT / "cases/S1-genesis-2of3/merged.json").read_bytes()
        b = (ROOT / "cases/S2-2024-2of3/merged.json").read_bytes()
        with self.assertRaises(merge.MergeRefused) as e:
            merge.merge([a, b], True)
        self.assertEqual(e.exception.check_id, "merge.unsigned-id")

    def test_a_refused_file_refuses_the_merge_with_its_check(self):
        a = (ROOT / "cases/S1-genesis-2of3/merged.json").read_bytes()
        with self.assertRaises(merge.MergeRefused) as e:
            merge.merge([a, a + b"\n"], True)
        self.assertEqual(e.exception.check_id, "canonical.form")


if __name__ == "__main__":
    unittest.main()
