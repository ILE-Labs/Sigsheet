"""The mainnet fetch's offline parts: the pinned digests, the comment format, the summary kept in the repository."""

import pathlib
import unittest

from sigsheet_vectors.mainnet import fetch
from sigsheet_vectors.sigsheet import canonical

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


class FetchTest(unittest.TestCase):
    def test_pinned_digests(self):
        digests = fetch.pinned_digests(ROOT)
        self.assertEqual(
            sorted(digests),
            [f"fiber-scripts-pr34/comment-{n}.txt" for n in range(1, 5)] + ["fiber-scripts-pr34/mainnet.json"],
        )
        self.assertEqual(
            digests["fiber-scripts-pr34/mainnet.json"],
            "8563ba8dcd0d051822dd0cc21db995dc8e6a2984e900d3500068f0185a07b51e",
        )

    def test_comment_signatures(self):
        text = "0x" + "ab" * 20 + ": 0x" + "cd" * 65 + "\nnot one: 0x" + "ef" * 65
        self.assertEqual(fetch.COMMENT_SIGNATURE.findall(text), ["0x" + "cd" * 65])

    def test_the_recorded_summaries_hold_no_chain_data(self):
        for case in (fetch.R1, fetch.R2):
            e = canonical.check((ROOT / "mainnet" / case / "expected.json").read_bytes())
            self.assertEqual(
                sorted(e),
                ["files", "final_transaction_hash", "id", "messages", "outcome", "ready", "source", "unsigned_id"],
            )
            self.assertTrue(e["ready"])
        r1 = canonical.check((ROOT / "mainnet" / fetch.R1 / "expected.json").read_bytes())
        self.assertEqual(r1["final_transaction_hash"], fetch.R1_COMMITTED)
        r2 = canonical.check((ROOT / "mainnet" / fetch.R2 / "expected.json").read_bytes())
        self.assertEqual(r2["final_transaction_hash"], fetch.R2_COMMITTED)


if __name__ == "__main__":
    unittest.main()
