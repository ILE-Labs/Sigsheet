"""The table of check ids: unique, ordered, each marked, and every id the code raises is in it."""

import pathlib
import re
import unittest

from sigsheet_vectors.sigsheet import check_ids

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "sigsheet_vectors"


class CheckIdsTest(unittest.TestCase):
    def test_ids_are_unique(self):
        ids = [c.id for c in check_ids.ALL]
        self.assertEqual(len(ids), len(set(ids)))

    def test_node_checks_and_only_they_need_a_node_and_say_why(self):
        for c in check_ids.ALL:
            self.assertEqual(c.needs_node, c in check_ids.NODE_CHECKS)
            self.assertEqual(bool(c.reason), c.needs_node)

    def test_every_id_in_the_code_is_in_the_table(self):
        pattern = re.compile(
            r'"((?:canonical|schema|transaction|context|headers|lock|multisig-configs|template|'
            r'inclusion-proofs|signatures|drop|merge)\.[a-z0-9-]+)"'
        )
        used = set()
        for path in (PACKAGE / "sigsheet").glob("*.py"):
            used |= set(pattern.findall(path.read_text(encoding="utf-8")))
        self.assertTrue(used)
        self.assertLessEqual(used, set(check_ids.IDS))


if __name__ == "__main__":
    unittest.main()
