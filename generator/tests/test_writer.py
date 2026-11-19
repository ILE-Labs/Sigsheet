"""The writer: which files are recorded inputs, and that a check finds every difference."""

import pathlib
import tempfile
import unittest

from sigsheet_vectors.vectors import writer


class WriterTest(unittest.TestCase):
    def test_recorded_inputs(self):
        for path in (
            "README.md",
            "cases/S1/input.json",
            "attacks/a/input.json",
            "mainnet/inputs.sha256",
            "mainnet/R1/expected.json",
        ):
            self.assertTrue(writer.recorded(path), path)
        for path in ("index.json", "cases/S1/expected.json", "cases/S1/partial/01-ab.json", "mainnet/R1/file.json"):
            self.assertFalse(writer.recorded(path), path)

    def test_differences_and_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "cases/a").mkdir(parents=True)
            (root / "cases/a/input.json").write_bytes(b"{}")
            (root / "cases/a/stale.json").write_bytes(b"x")
            (root / "mainnet/.fetched").mkdir(parents=True)
            (root / "mainnet/.fetched/ignored.json").write_bytes(b"y")
            built = {"cases/a/input.json": b"{}", "cases/a/file.json": b"1", "index.json": b"2"}
            found = writer.differences(root, built)
            self.assertEqual(
                found,
                ["missing: cases/a/file.json", "missing: index.json", "not built by the generator: cases/a/stale.json"],
            )
            writer.write(root, built)
            self.assertEqual(writer.differences(root, built), [])
            self.assertFalse((root / "cases/a/stale.json").exists())
            self.assertTrue((root / "mainnet/.fetched/ignored.json").exists())
            (root / "index.json").write_bytes(b"3")
            self.assertEqual(writer.differences(root, built), ["differs: index.json"])


if __name__ == "__main__":
    unittest.main()
