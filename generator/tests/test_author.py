"""Authoring makes inputs the reader accepts, with signatures that verify; it writes nothing here."""

import unittest

from sigsheet_vectors import author
from sigsheet_vectors.sigsheet import reader, signatures
from sigsheet_vectors.vectors import cases


class AuthorTest(unittest.TestCase):
    def test_synthetic_cases(self):
        for name, inp in author.case_inputs().items():
            data = cases.encode(cases.with_signatures(cases.sheet_from_input(inp), cases.recorded_signatures(inp)))
            v = signatures.verify(reader.read(data))
            self.assertEqual(v.dropped, (), name)
            self.assertEqual(
                sum(len(e) for e in v.signatures.values()) + sum(len(e) for e in v.carried.values()),
                len(inp["signatures"]),
            )

    def test_keys_never_leave_memory(self):
        k = author.Key()
        self.assertEqual(len(k.hash), 20)
        self.assertFalse(any(isinstance(x, bytes) and len(x) == 32 for x in vars(k).values() if x is not k._secret))


if __name__ == "__main__":
    unittest.main()
