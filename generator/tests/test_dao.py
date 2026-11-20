"""The DAO arithmetic against the node's own figures for the two-deposit withdrawal (XRTb-3)."""

import json
import pathlib
import unittest

from sigsheet_vectors.ckb import dao, rpc_json
from sigsheet_vectors.ckb.molecule import CellOutput, Script

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


class DaoTest(unittest.TestCase):
    def setUp(self):
        inp = json.loads((ROOT / "cases/dao-two-deposits/input.json").read_bytes())
        self.inp = inp
        self.tx = rpc_json.transaction_from(inp["transaction"], "tx")
        node = inp["node"]
        self.headers = {bytes.fromhex(h[2:]): rpc_json.header_view_from(v, h) for h, v in node["get_header"].items()}
        self.prev = {bytes.fromhex(h[2:]): a["transaction"] for h, a in node["get_transaction"].items()}
        self.proofs = {
            bytes.fromhex(h[2:]): rpc_json.proof_from(p, h) for h, p in node["get_transaction_proof"].items()
        }

    def test_amounts_and_minimal_since_equal_the_nodes(self):
        recorded = self.inp["recorded"]
        for i, cell_input in enumerate(self.tx.raw.inputs):
            op = cell_input.previous_output
            prev = rpc_json.transaction_from(
                {k: v for k, v in self.prev[op.tx_hash].items() if k != "hash"}, "prev"
            ).raw
            output, data = prev.outputs[op.index], prev.outputs_data[op.index]
            number = dao.withdrawing_deposit_number(output, data)
            self.assertIsNotNone(number)
            index = dao.deposit_header_index(self.tx.witnesses[i])
            self.assertEqual(index, i)
            deposit = self.headers[self.tx.raw.header_deps[index]]
            self.assertEqual(deposit.number, number)
            withdraw = self.headers[self.proofs[op.tx_hash].block_hash]
            self.assertEqual(str(dao.maximum_withdraw(output, data, deposit, withdraw)), recorded["dao_amount"][i])
            self.assertEqual(hex(dao.minimal_since(deposit, withdraw)), recorded["dao_minimal_since"][i])
            self.assertIsNone(dao.minimal_since(withdraw, deposit))

    def test_occupied_capacity(self):
        lock = Script(bytes(32), "type", bytes(20))
        self.assertEqual(dao.occupied_capacity(CellOutput(0, lock, None), 0), 61 * 100_000_000)
        self.assertEqual(dao.occupied_capacity(CellOutput(0, lock, dao.DAO_TYPE), 8), (61 + 33 + 8) * 100_000_000)

    def test_deposit_index_is_the_first_byte_of_an_8_byte_input_type(self):
        from sigsheet_vectors.ckb.molecule import WitnessArgs, encode_witness_args

        self.assertEqual(dao.deposit_header_index(encode_witness_args(WitnessArgs(None, bytes([3]) + bytes(7)))), 3)
        self.assertEqual(dao.deposit_header_index(encode_witness_args(WitnessArgs(None, bytes([3, 1]) + bytes(6)))), 3)
        self.assertIsNone(dao.deposit_header_index(encode_witness_args(WitnessArgs(None, bytes(4)))))
        self.assertIsNone(dao.deposit_header_index(b""))

    def test_a_deposited_cell_is_no_withdrawing_cell(self):
        self.assertIsNone(
            dao.withdrawing_deposit_number(CellOutput(1, Script(bytes(32), "type", b""), dao.DAO_TYPE), bytes(8))
        )


if __name__ == "__main__":
    unittest.main()
