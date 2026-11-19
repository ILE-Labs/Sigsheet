"""The case vectors (issue #5) and how each one is built from its `input.json`.

`input.json` holds a case's recorded inputs: the built transaction with its witness templates, the multisig configs,
either the file's other fields as recorded or the node's answers for creating it, every recorded signature with the
group and signer it is filed under, and the design-stage results the vector must reproduce. Building a case writes:
`file.json`, the file as created; one `partial/<nn>-<signer>.json` per recorded signature, the created file plus that
one signature; `merged.json`, the merge of every partial file; `final-tx.json` when every group version 1 signs is
ready; and `expected.json`. A recorded result that the rules don't reproduce stops the build.
"""

import hashlib
from dataclasses import dataclass

from ..ckb import rpc_json
from ..ckb.molecule import transaction_hash
from ..ckb.rpc_json import fmt_bytes, parse_bytes
from ..sigsheet import canonical, finalize, merge, reader, schema, show, signatures
from ..sigsheet.create import create
from ..sigsheet.messages import message


@dataclass(frozen=True, slots=True)
class Case:
    id: str
    source: str
    expect: str = "accepted"


CASES = (
    Case("S1-genesis-2of3", "X2 S1"),
    Case("S2-2024-2of3", "X2 S2"),
    Case("S3-v2-2of3-two-inputs", "X2 S3"),
    Case("S4-v2-first-R", "X2 S4"),
    Case("S4N-v2-first-R-missing-required", "X2 S4N"),
    Case("S5-v2-since-in-args", "X2 S5"),
    Case("S6-two-multisig-groups", "X2 S6"),
    Case("S7-multisig-plus-single-key", "X2 S7"),
    Case("S8-neuron-export", "X2 S8"),
    Case("S9-extra-witness", "X2 S9"),
    Case("S10-same-script-two-deployments", "X3 S10"),
    Case("S11-same-script-20-and-28-byte-args", "X3 S11"),
    Case("R1-35-first-member-required", "X3 R1-35"),
    Case("dao-two-deposits", "XRTb-3"),
    Case("dao-two-deposits-no-proofs", "XRTb-3"),
    Case("dao-proof-block-changed", "XRTb-3", "inclusion-proofs.verify"),
    Case("dao-cut-output", "XRTb-3"),
    Case("creation-c1", "XRT-4 C1"),
    Case("unknown-lock-partial", "XRT-3"),
    Case("omnilock-multisig-carried", "XRTb-2 F07"),
    Case("genesis-n12-m2-skip-10", "XRT-1"),
    Case("genesis-n12-m2-10-11-not-ready", "XRT-1"),
    Case("genesis-n12-m11-r11", "XRTb-1"),
    Case("genesis-n20-m1-18-not-ready", "XRT-1"),
)


class VectorMismatch(AssertionError):
    """A vector's result differs from what it must reproduce."""


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def encode(sheet: schema.Sheet) -> bytes:
    return canonical.encode(schema.to_json(sheet))


def sheet_from_input(inp: dict) -> schema.Sheet:
    """The created file, without signatures."""
    if "node" in inp:
        tx = rpc_json.transaction_from(inp["transaction"], "transaction")
        configs = schema.from_json(
            {
                "version": schema.VERSION,
                "transaction": inp["transaction"],
                "context": {},
                "headers": {},
                "inclusion_proofs": {},
                "multisig_configs": inp["multisig_configs"],
                "signatures": {},
            }
        ).multisig_configs
        return create(tx, inp["node"], configs)
    fields = ("transaction", "context", "headers", "inclusion_proofs", "multisig_configs")
    return schema.from_json({"version": schema.VERSION, "signatures": {}, **{f: inp[f] for f in fields}})


def with_signatures(sheet: schema.Sheet, entries: list[tuple[bytes, bytes, bytes]]) -> schema.Sheet:
    sigs: dict[bytes, dict[bytes, bytes]] = {}
    for group, signer, sig in entries:
        sigs.setdefault(group, {})[signer] = sig
    return schema.Sheet(
        sheet.transaction, sheet.context, sheet.headers, sheet.inclusion_proofs, sheet.multisig_configs, sigs
    )


def recorded_signatures(inp: dict) -> list[tuple[bytes, bytes, bytes]]:
    return [
        (
            parse_bytes(e["group"], "group", 32),
            parse_bytes(e["signer"], "signer", 20),
            parse_bytes(e["signature"], "signature", 65),
        )
        for e in inp["signatures"]
    ]


def drops_json(v: signatures.Verified) -> tuple[list, list]:
    dropped = [{"group": fmt_bytes(d.group), "signer": fmt_bytes(d.signer), "reason": d.reason} for d in v.dropped]
    normalized = [{"group": fmt_bytes(g), "signer": fmt_bytes(s)} for g, s in v.normalized]
    return dropped, normalized


def outcome_of(data: bytes, development_chain: bool) -> dict:
    """What a reader does with a file: refused with its check id, or accepted with its drops, status and view."""
    try:
        accepted = reader.read(data, development_chain)
    except reader.Refused as e:
        return {"outcome": "refused", "check": e.check_id}
    v = signatures.verify(accepted)
    dropped, normalized = drops_json(v)
    sts = finalize.status(accepted, v)
    known = [s for s in sts.values() if s is not None]
    return {
        "outcome": "accepted",
        "dropped": dropped,
        "normalized": normalized,
        "ready": bool(known) and all(s.ready for s in known),
        "shown": show.view(accepted, v),
        "_accepted": accepted,
        "_verified": v,
    }


def final_transaction(accepted: reader.Accepted, verified: signatures.Verified) -> tuple[bytes, bool] | None:
    try:
        tx, partial = finalize.finalize(accepted, verified)
    except finalize.NotReady:
        return None
    return canonical.encode(rpc_json.transaction_to(tx)), partial


def build(case_id: str, input_bytes: bytes, expect: str = "accepted") -> dict[str, bytes]:
    """Every file of one case vector, by its path inside the vector's folder."""
    inp = canonical.check(input_bytes)
    development_chain = inp["chain"] == "devnet"
    created = sheet_from_input(inp)
    files = {"input.json": input_bytes, "file.json": encode(created)}
    first = outcome_of(files["file.json"], development_chain)
    if first["outcome"] == "refused":
        if expect != first["check"]:
            raise VectorMismatch(f"{case_id}: refused with {first['check']}, expected {expect}")
        expected = {"id": case_id, "outcome": "refused", "check": first["check"]}
        expected["files"] = {name: sha256(b) for name, b in sorted(files.items())}
        files["expected.json"] = canonical.encode(expected)
        return files
    if expect != "accepted":
        raise VectorMismatch(f"{case_id}: accepted, expected {expect}")

    entries = recorded_signatures(inp)
    for n, (group, signer, sig) in enumerate(entries, 1):
        files[f"partial/{n:02d}-{signer.hex()}.json"] = encode(with_signatures(created, [(group, signer, sig)]))
    partials = [b for name, b in files.items() if name.startswith("partial/")]
    files["merged.json"] = merge.merge(partials, development_chain) if partials else files["file.json"]
    result = outcome_of(files["merged.json"], development_chain)
    accepted, verified = result.pop("_accepted"), result.pop("_verified")
    final = final_transaction(accepted, verified)
    if final is not None:
        files["final-tx.json"] = final[0]

    messages = {fmt_bytes(h): fmt_bytes(message(accepted, g)) for h, g in accepted.groups.items() if g.kind is not None}
    expected = {
        "id": case_id,
        "outcome": "accepted",
        "unsigned_id": fmt_bytes(accepted.unsigned_id),
        "transaction_hash": fmt_bytes(transaction_hash(accepted.sheet.transaction.raw)),
        "messages": messages,
        "dropped": result["dropped"],
        "normalized": result["normalized"],
        "ready": result["ready"],
        "shown": result["shown"],
        "final": None if final is None else {"partial": final[1]},
    }
    _check_recorded(case_id, inp.get("recorded", {}), expected, final)
    expected["files"] = {name: sha256(b) for name, b in sorted(files.items())}
    files["expected.json"] = canonical.encode(expected)
    return files


def _check_recorded(case_id: str, recorded: dict, expected: dict, final) -> None:
    for group, msg in recorded.get("messages", {}).items():
        if expected["messages"].get(group) != msg:
            raise VectorMismatch(f"{case_id}: group {group}'s message isn't the recorded one")
    committed = recorded.get("committed")
    if committed is not None:
        if final is None:
            raise VectorMismatch(f"{case_id}: no final transaction, where one was committed")
        tx = canonical.decode(final[0])
        if fmt_bytes(transaction_hash(rpc_json.transaction_from(tx, "final").raw)) != committed["hash"]:
            raise VectorMismatch(f"{case_id}: the final transaction's hash isn't the committed one")
        if "witnesses" in committed and tx["witnesses"] != committed["witnesses"]:
            raise VectorMismatch(f"{case_id}: the final witnesses aren't the committed ones")
    fee = recorded.get("fee")
    if fee is not None:
        shown = expected["shown"]["fee"]
        if (shown["kind"], shown["shannons"]) != (fee["kind"], fee["shannons"]):
            raise VectorMismatch(
                f"{case_id}: fee {shown['kind']} {shown['shannons']}, recorded {fee['kind']} {fee['shannons']}"
            )
    for field in ("amount", "minimal_since"):
        want = recorded.get(f"dao_{field}")
        if want is not None and [d[field] for d in expected["shown"]["fee"]["dao_inputs"]] != want:
            raise VectorMismatch(f"{case_id}: the DAO inputs' {field} differ from the recorded ones")
    if "ready" in recorded and expected["ready"] != recorded["ready"]:
        raise VectorMismatch(f"{case_id}: ready is {expected['ready']}, recorded {recorded['ready']}")
