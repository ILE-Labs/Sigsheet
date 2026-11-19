"""RFC 8785 serialization for the Sigsheet domain, and the canonical check."""

import unittest

from sigsheet_vectors.sigsheet import canonical
from sigsheet_vectors.sigsheet.canonical import CanonicalError


class EncodeTest(unittest.TestCase):
    def test_no_whitespace_and_sorted_keys_at_every_level(self):
        v = {"b": [3, {"z": None, "a": True}], "a": "x", "A": False}
        self.assertEqual(canonical.encode(v), b'{"A":false,"a":"x","b":[3,{"a":true,"z":null}]}')

    def test_keys_sort_by_code_point(self):
        self.assertEqual(canonical.encode({"_": 1, "Z": 2, "0x": 3, "a": 4}), b'{"0x":3,"Z":2,"_":1,"a":4}')

    def test_string_escapes(self):
        s = '"\\/\b\t\n\f\r\x00\x1f\x7f'
        self.assertEqual(canonical.encode(s), b'"\\"\\\\/\\b\\t\\n\\f\\r\\u0000\\u001f\x7f"')

    def test_integers(self):
        self.assertEqual(canonical.encode([0, -1, 2**53 - 1]), b"[0,-1,9007199254740991]")

    def test_outside_the_domain(self):
        for bad in (1.5, 2**53, "é", {1: "a"}, (1,), b"x"):
            with self.assertRaises(CanonicalError, msg=repr(bad)):
                canonical.encode(bad)


class CheckTest(unittest.TestCase):
    def test_round_trip(self):
        data = b'{"a":[1,"0x"],"b":null}'
        self.assertEqual(canonical.check(data), {"a": [1, "0x"], "b": None})

    def test_refusals(self):
        cases = {
            b'{"a":1.0}': "canonical.json",
            b'{"a":1e2}': "canonical.json",
            b'{"a":NaN}': "canonical.json",
            b'{"a":1,"a":2}': "canonical.json",
            b'{"a":"\xc3\xa9"}': "canonical.json",
            b"{": "canonical.json",
            b'{"b":1,"a":2}': "canonical.form",
            b'{"a": 1}': "canonical.form",
            b'{"a":1}\n': "canonical.form",
            b'{"a":"\\u0041"}': "canonical.form",
            b'{"a":-0}': "canonical.form",
        }
        for data, check_id in cases.items():
            with self.assertRaises(CanonicalError, msg=data) as e:
                canonical.check(data)
            self.assertEqual(e.exception.check_id, check_id, data)


if __name__ == "__main__":
    unittest.main()
