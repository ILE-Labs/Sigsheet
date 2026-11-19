"""The RPC JSON forms and the hex rules."""

import unittest

from sigsheet_vectors.ckb import rpc_json
from sigsheet_vectors.ckb.rpc_json import JsonShapeError


class HexRulesTest(unittest.TestCase):
    def test_integers(self):
        self.assertEqual(rpc_json.parse_uint("0x0", 64, "x"), 0)
        self.assertEqual(rpc_json.parse_uint("0x2540be400", 64, "x"), 10_000_000_000)
        for bad in ("0x01", "0x", "0xA", "10", "0x1g", 1):
            with self.assertRaises(JsonShapeError, msg=bad):
                rpc_json.parse_uint(bad, 64, "x")
        with self.assertRaises(JsonShapeError):
            rpc_json.parse_uint("0x100000000", 32, "x")

    def test_bytes(self):
        self.assertEqual(rpc_json.parse_bytes("0x", "x"), b"")
        self.assertEqual(rpc_json.parse_bytes("0x00ff", "x"), b"\x00\xff")
        for bad in ("0x0", "0xFF", "00", "0xzz"):
            with self.assertRaises(JsonShapeError, msg=bad):
                rpc_json.parse_bytes(bad, "x")
        with self.assertRaises(JsonShapeError):
            rpc_json.parse_bytes("0x00", "x", 32)

    def test_formatting_is_the_parsed_form(self):
        for n in (0, 1, 255, 1 << 63):
            self.assertEqual(rpc_json.parse_uint(rpc_json.fmt_uint(n), 64, "x"), n)


class ShapesTest(unittest.TestCase):
    SCRIPT = {"code_hash": "0x" + "11" * 32, "hash_type": "type", "args": "0x"}

    def test_exact_fields(self):
        rpc_json.script_from(self.SCRIPT, "s")
        with self.assertRaises(JsonShapeError):
            rpc_json.script_from({**self.SCRIPT, "extra": 1}, "s")
        with self.assertRaises(JsonShapeError):
            rpc_json.script_from({**self.SCRIPT, "hash_type": "Type"}, "s")
        with self.assertRaises(JsonShapeError):
            rpc_json.cell_output_from({"capacity": "0x1", "lock": self.SCRIPT}, "o")

    def test_an_absent_type_is_null(self):
        out = rpc_json.cell_output_from({"capacity": "0x1", "lock": self.SCRIPT, "type": None}, "o")
        self.assertIsNone(out.type)
        self.assertEqual(rpc_json.cell_output_to(out)["type"], None)

    def test_a_transaction_has_no_hash_field(self):
        tx = {
            "version": "0x0",
            "cell_deps": [],
            "header_deps": [],
            "inputs": [],
            "outputs": [],
            "outputs_data": [],
            "witnesses": [],
        }
        self.assertEqual(rpc_json.transaction_to(rpc_json.transaction_from(tx, "t")), tx)
        with self.assertRaises(JsonShapeError):
            rpc_json.transaction_from({**tx, "hash": "0x" + "00" * 32}, "t")


if __name__ == "__main__":
    unittest.main()
