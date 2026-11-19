"""Creating a file from recorded node answers, byte for byte, and refusing answers that don't hash."""

import copy
import pathlib
import unittest

from sigsheet_vectors.ckb import rpc_json
from sigsheet_vectors.sigsheet import canonical, create, schema

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


def load(case: str) -> dict:
    return canonical.check((ROOT / "cases" / case / "input.json").read_bytes())


def created(case: str) -> schema.Sheet:
    inp = load(case)
    tx = rpc_json.transaction_from(inp["transaction"], "tx")
    configs = {bytes.fromhex(k[2:]): schema.config_from_json(v, k) for k, v in inp["multisig_configs"].items()}
    return create.create(tx, inp["node"], configs)


class CreateTest(unittest.TestCase):
    def test_created_files_equal_the_vectors(self):
        for case in ("creation-c1", "dao-two-deposits", "dao-two-deposits-no-proofs", "dao-cut-output"):
            data = canonical.encode(schema.to_json(created(case)))
            self.assertEqual(data, (ROOT / "cases" / case / "file.json").read_bytes(), case)

    def test_proofs_are_carried_only_when_the_node_gave_them(self):
        self.assertEqual(created("dao-two-deposits-no-proofs").inclusion_proofs, {})
        self.assertEqual(len(created("dao-two-deposits").inclusion_proofs), 2)

    def test_a_node_answer_that_doesnt_hash_is_refused(self):
        inp = load("creation-c1")
        bad = copy.deepcopy(inp["node"])
        answer = next(iter(bad["get_transaction"].values()))
        answer["transaction"]["outputs"][0]["capacity"] = "0x1"
        tx = rpc_json.transaction_from(inp["transaction"], "tx")
        with self.assertRaises(create.CreateError):
            create.create(tx, bad, {})
        with self.assertRaises(create.CreateError):
            create.create(tx, {}, {})


if __name__ == "__main__":
    unittest.main()
