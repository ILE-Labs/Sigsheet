"""The command line's check on the committed vectors."""

import contextlib
import io
import unittest

from sigsheet_vectors import __main__ as cli


class MainTest(unittest.TestCase):
    def test_check_passes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["check"]), 0)
        self.assertIn("every vector rebuilds byte for byte", out.getvalue())


if __name__ == "__main__":
    unittest.main()
