"""The seven fields, to and from the parsed value, on every vector file."""

import pathlib
import unittest

from sigsheet_vectors.sigsheet import canonical, schema

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


class SchemaTest(unittest.TestCase):
    def test_every_vector_file_round_trips(self):
        files = (
            sorted(ROOT.glob("cases/*/file.json"))
            + sorted(ROOT.glob("cases/*/merged.json"))
            + sorted(ROOT.glob("cases/*/partial/*.json"))
        )
        self.assertGreater(len(files), 50)
        for path in files:
            data = path.read_bytes()
            self.assertEqual(canonical.encode(schema.to_json(schema.from_json(canonical.check(data)))), data, path)

    def test_the_fields_are_exactly_seven(self):
        self.assertEqual(len(schema.TOP_LEVEL), 7)
        v = canonical.check((ROOT / "cases/S1-genesis-2of3/file.json").read_bytes())
        self.assertEqual(sorted(v), sorted(schema.TOP_LEVEL))

    def test_config_script_and_key(self):
        c = schema.MultisigConfig(1, 2, (b"\x11" * 20, b"\x22" * 20, b"\x33" * 20))
        self.assertEqual(c.script(), bytes([0, 1, 2, 3]) + b"\x11" * 20 + b"\x22" * 20 + b"\x33" * 20)
        self.assertEqual(len(c.key()), 20)


if __name__ == "__main__":
    unittest.main()
