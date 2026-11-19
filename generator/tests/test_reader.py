"""Every reader check refuses its own mutation, and the checks run in the specification's order."""

import copy
import pathlib
import unittest

from sigsheet_vectors.ckb import molecule, rpc_json
from sigsheet_vectors.sigsheet import canonical, check_ids, reader

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


def value(path: str) -> dict:
    return canonical.check((ROOT / path).read_bytes())


def refusal(v) -> str | None:
    data = v if isinstance(v, bytes) else canonical.encode(v)
    try:
        reader.read(data, development_chain=True)
    except reader.Refused as e:
        return e.check_id
    return None


def rekey(v: dict, old: str) -> dict:
    """Re-key a changed context entry by its new hash, and point the inputs at it."""
    raw = rpc_json.raw_transaction_from(v["context"][old], old)
    new = rpc_json.fmt_bytes(molecule.transaction_hash(raw))
    v["context"][new] = v["context"].pop(old)
    for i in v["transaction"]["inputs"]:
        if i["previous_output"]["tx_hash"] == old:
            i["previous_output"]["tx_hash"] = new
    return v


class ReaderChecksTest(unittest.TestCase):
    def setUp(self):
        self.s1 = value("cases/S1-genesis-2of3/merged.json")
        self.dao = value("cases/dao-two-deposits/merged.json")
        self.prev = next(iter(self.s1["context"]))
        self.cfg = next(iter(self.s1["multisig_configs"]))

    def refuses(self, check_id: str, mutate, base: str = "s1"):
        v = copy.deepcopy(getattr(self, base))
        mutate(v)
        self.assertEqual(refusal(v), check_id)

    def test_the_vectors_are_accepted(self):
        self.assertIsNone(refusal(self.s1))
        self.assertIsNone(refusal(self.dao))

    def test_canonical_json(self):
        good = canonical.encode(self.s1)
        for bad in (
            good.replace(b'"0x1"', b'"0x1\xc3\xa9"', 1),
            good.replace(b'"threshold":2', b'"threshold":2.0'),
            good.replace(b'"threshold":2', b'"threshold":NaN'),
            b'{"version":"0x1","version":"0x1"}',
            good.replace(b'"threshold":2', b'"threshold":9007199254740993'),
        ):
            self.assertEqual(refusal(bad), "canonical.json")

    def test_canonical_form(self):
        good = canonical.encode(self.s1)
        for bad in (
            good + b"\n",
            b" " + good,
            good.replace(b'":', b'": ', 1),
            good.replace(b'"version":"0x1"', b'"version":"\\u0030x1"'),
        ):
            self.assertEqual(refusal(bad), "canonical.form")

    def test_schema(self):
        self.refuses("schema.fields", lambda v: v.update(description="routine payout"))
        self.refuses("schema.version", lambda v: v.update(version="0x2"))
        self.refuses("schema.transaction", lambda v: v["transaction"]["outputs"][0].update(capacity="0x2540BE400"))
        self.refuses("schema.transaction", lambda v: v["transaction"].update(hash="0x" + "00" * 32))
        self.refuses("schema.context", lambda v: v["context"][self.prev].update(witnesses=[]))
        self.refuses("schema.headers", lambda v: next(iter(v["headers"].values())).pop("nonce"), "dao")
        self.refuses(
            "schema.inclusion-proofs", lambda v: next(iter(v["inclusion_proofs"].values())).pop("witnesses_root"), "dao"
        )
        self.refuses("schema.multisig-configs", lambda v: v["multisig_configs"][self.cfg].update(threshold="0x2"))
        self.refuses("schema.multisig-configs", lambda v: v["multisig_configs"][self.cfg].update(threshold=256))
        self.refuses("schema.signatures", lambda v: v["signatures"].update({next(iter(v["signatures"])): {}}))
        self.refuses(
            "schema.signatures",
            lambda v: next(iter(v["signatures"].values())).update({"0x" + "11" * 20: "0x" + "00" * 64}),
        )

    def test_transaction(self):
        self.refuses("transaction.outputs-data", lambda v: v["transaction"]["outputs_data"].pop())
        self.refuses(
            "transaction.duplicate-input",
            lambda v: v["transaction"]["inputs"].append(copy.deepcopy(v["transaction"]["inputs"][0])),
        )

    def test_context(self):
        def falsify(v):
            out = v["context"][self.prev]["outputs"][0]
            out["capacity"] = hex(int(out["capacity"], 16) + 1)

        self.refuses("context.hash", falsify)
        self.refuses("context.missing", lambda v: v["transaction"]["inputs"][0]["previous_output"].update(index="0x63"))
        s10 = value("cases/S10-same-script-two-deployments/input.json")["context"]
        self.refuses("context.unused", lambda v: v["context"].update(s10))

    def test_headers(self):
        def change_nonce(v):
            h = next(iter(v["headers"].values()))
            h["nonce"] = hex(int(h["nonce"], 16) ^ 1)

        self.refuses("headers.hash", change_nonce, "dao")
        self.refuses("headers.missing", lambda v: v["headers"].pop(next(iter(v["headers"]))), "dao")
        self.refuses("headers.unused", lambda v: v["headers"].update(dict([next(iter(self.dao["headers"].items()))])))

    def test_lock_args(self):
        self.assertEqual(refusal(value("attacks/single-key-args-32/attack.json")), "lock.single-key-args")

        def args_21(v):
            v["context"][self.prev]["outputs"][0]["lock"]["args"] += "00"
            return rekey(v, self.prev)

        self.refuses("lock.multisig-args", args_21)

    def test_configs(self):
        self.refuses("multisig-configs.values", lambda v: v["multisig_configs"][self.cfg].update(threshold=0))
        self.refuses("multisig-configs.values", lambda v: v["multisig_configs"][self.cfg].update(require_first_n=3))

        def repeat(v):
            keys = v["multisig_configs"][self.cfg]["public_key_hashes"]
            keys[1] = keys[0]

        self.refuses("multisig-configs.repeated-key", repeat)
        self.refuses(
            "multisig-configs.hash",
            lambda v: v["multisig_configs"][self.cfg]["public_key_hashes"].__setitem__(0, "0x" + "ee" * 20),
        )
        self.assertEqual(refusal(value("attacks/unused-config/attack.json")), "multisig-configs.unused")
        self.refuses("multisig-configs.missing", lambda v: v["multisig_configs"].clear())

    def test_templates(self):
        self.refuses("template.missing", lambda v: v["transaction"].update(witnesses=[]))
        lock = molecule.encode_witness_args(molecule.WitnessArgs(b"\x00" * 65))
        empty = molecule.encode_witness_args(molecule.WitnessArgs())
        for w in (lock, empty, b"\x01\x02"):
            self.refuses(
                "template.form", lambda v, w=w: v["transaction"]["witnesses"].__setitem__(0, rpc_json.fmt_bytes(w))
            )
        self.assertEqual(refusal(value("attacks/template-fourth-field/attack.json")), "template.form")

    def test_inclusion_proofs(self):
        def move_proof(v):
            h, p = v["inclusion_proofs"].popitem()
            v["inclusion_proofs"]["0x" + "ab" * 32] = p

        self.refuses("inclusion-proofs.target", move_proof, "dao")
        self.refuses(
            "inclusion-proofs.header",
            lambda v: next(iter(v["inclusion_proofs"].values())).update(block_hash="0x" + "ab" * 32),
            "dao",
        )
        self.assertEqual(refusal(value("cases/dao-proof-block-changed/file.json")), "inclusion-proofs.verify")

    def test_carried_limit(self):
        v = value("cases/unknown-lock-partial/merged.json")
        group = next(g for g in v["signatures"] if len(v["signatures"][g]) == 1)
        v["signatures"][group] = {f"0x{i:040x}": "0x" + "00" * 65 for i in range(256)}
        self.assertEqual(refusal(v), "signatures.carried-limit")
        v["signatures"][group] = {f"0x{i:040x}": "0x" + "00" * 65 for i in range(255)}
        self.assertIsNone(refusal(v))

    def test_the_first_failing_check_in_order_is_reported(self):
        def two_faults(v):
            v["transaction"]["witnesses"][0] = rpc_json.fmt_bytes(molecule.encode_witness_args(molecule.WitnessArgs()))
            out = v["context"][self.prev]["outputs"][0]
            out["capacity"] = hex(int(out["capacity"], 16) + 1)

        self.refuses("context.hash", two_faults)
        order = [c.id for c in check_ids.READER_CHECKS]
        self.assertLess(order.index("context.hash"), order.index("template.form"))


if __name__ == "__main__":
    unittest.main()
