"""Integration: rebuilding every vector in memory gives the committed bytes, twice."""

import unittest

from sigsheet_vectors import __main__ as cli
from sigsheet_vectors.vectors import writer


class RebuildTest(unittest.TestCase):
    def test_check_passes_on_the_committed_vectors(self):
        first = cli.build_all(cli.ROOT)
        self.assertEqual(writer.differences(cli.ROOT, first), [])
        self.assertEqual(cli.build_all(cli.ROOT), first)


if __name__ == "__main__":
    unittest.main()
