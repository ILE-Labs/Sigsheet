"""Molecule round trips, the node's hashes, and strict decoding."""

import json
import pathlib
import unittest

from sigsheet_vectors.ckb import molecule, rpc_json

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


def load(path: str):
    return json.loads((ROOT / path).read_text())


class RoundTripTest(unittest.TestCase):
    def test_transactions_round_trip_and_hash_as_the_node_does(self):
        # A node's get_transaction answer holds the transaction and the hash the node computed.
        node = load("cases/dao-two-deposits/input.json")["node"]
        for h, answer in node["get_transaction"].items():
            tx = rpc_json.transaction_from({k: v for k, v in answer["transaction"].items() if k != "hash"}, h)
            b = molecule.encode_transaction(tx)
            self.assertEqual(molecule.decode_transaction(b), tx)
            self.assertEqual(molecule.encode_transaction(molecule.decode_transaction(b)), b)
            self.assertEqual(rpc_json.fmt_bytes(molecule.transaction_hash(tx.raw)), h)

    def test_headers_round_trip_and_hash_as_the_node_does(self):
        for h, view in load("cases/dao-two-deposits/input.json")["node"]["get_header"].items():
            header = rpc_json.header_from({k: v for k, v in view.items() if k != "hash"}, h)
            b = molecule.encode_header(header)
            self.assertEqual(len(b), molecule.HEADER_SIZE)
            self.assertEqual(molecule.decode_header(b), header)
            self.assertEqual(rpc_json.fmt_bytes(molecule.header_hash(header)), h)

    def test_context_entries_hash_to_their_keys(self):
        for h, raw in load("cases/S7-multisig-plus-single-key/input.json")["context"].items():
            t = rpc_json.raw_transaction_from(raw, h)
            self.assertEqual(molecule.decode_raw_transaction(molecule.encode_raw_transaction(t)), t)
            self.assertEqual(rpc_json.fmt_bytes(molecule.transaction_hash(t)), h)

    def test_witness_args_and_scripts(self):
        for w in (
            molecule.WitnessArgs(),
            molecule.WitnessArgs(b"\x01" * 65),
            molecule.WitnessArgs(None, bytes(8), b"\x02"),
        ):
            b = molecule.encode_witness_args(w)
            self.assertEqual(molecule.decode_witness_args(b), w)
        s = molecule.Script(bytes(range(32)), "data1", b"\xaa\xbb")
        self.assertEqual(molecule.decode_script(molecule.encode_script(s)), s)
        points = [molecule.OutPoint(bytes([i]) * 32, i) for i in range(3)]
        self.assertEqual(molecule.decode_out_point_vec(molecule.encode_out_point_vec(points)), points)

    def test_empty_witness_args_is_16_bytes(self):
        self.assertEqual(molecule.encode_witness_args(molecule.WitnessArgs()).hex(), "10000000100000001000000010000000")


class StrictDecodingTest(unittest.TestCase):
    def test_a_fourth_field_is_refused(self):
        four = molecule.dynvec([b"", molecule.encode_bytes(b"\x07"), b"", molecule.encode_bytes(b"\x01\x02")])
        with self.assertRaises(molecule.MoleculeError):
            molecule.decode_witness_args(four)

    def test_inconsistent_sizes_are_refused(self):
        good = molecule.encode_witness_args(molecule.WitnessArgs(b"\x01"))
        for bad in (good[:-1], good + b"\x00", b"\x08\x00\x00\x00\x04\x00\x00\x00", b"\x01\x02"):
            with self.assertRaises(molecule.MoleculeError):
                molecule.decode_witness_args(bad)
        with self.assertRaises(molecule.MoleculeError):
            molecule.decode_bytes(b"\x02\x00\x00\x00\x01")

    def test_out_of_range_integers_are_refused(self):
        with self.assertRaises(molecule.MoleculeError):
            molecule.uint(1 << 32, 4)
        with self.assertRaises(molecule.MoleculeError):
            molecule.uint(-1, 8)


if __name__ == "__main__":
    unittest.main()
