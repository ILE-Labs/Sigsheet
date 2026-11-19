"""The attack vectors (issue #6): each one changes an honest base vector's file, or is a synthetic file.

Each attack declares the result its design-stage experiment showed (X4, XRT-2, XRT-3, XRTb-2), as the v0.1 rules
state it: the file refused with a check id, or accepted with named signatures dropped; whether it is ready; and the
merge with its honest base, run in both orders: refused with a check id, or equal to the base's merged file (and so to
its final transaction). Building an attack computes every result from the rules and stops when one differs from the
declaration. The attacks are built on recorded devnet cases and synthetic files, never on the mainnet cases, so they
run offline.
"""

import copy
from dataclasses import dataclass

from ..ckb.rpc_json import fmt_bytes
from ..sigsheet import canonical, merge
from ..sigsheet.messages import message
from . import cases


@dataclass(frozen=True, slots=True)
class Attack:
    id: str
    outcome: str
    dropped: tuple[str, ...] = ()
    ready: bool | None = None
    final: str | None = None
    merge: str | None = None
    warnings: tuple[str, ...] = ()


ATTACKS = (
    Attack("falsified-input-cell", "context.hash", merge="context.hash"),
    Attack("swapped-transaction", "accepted", ("drop.mismatch", "drop.mismatch"), False, merge="merge.unsigned-id"),
    Attack("altered-output", "accepted", ("drop.mismatch", "drop.mismatch"), False, merge="merge.unsigned-id"),
    Attack("non-member-signature", "accepted", ("drop.not-member",), True, "base", "base"),
    Attack("junk-signatures", "accepted", ("drop.mismatch", "drop.not-member"), True, "base", "base"),
    Attack("many-junk-entries", "accepted", ("drop.not-member",) * 32, True, "base", "base"),
    Attack("swapped-config", "multisig-configs.hash", merge="multisig-configs.hash"),
    Attack("display-field", "schema.fields", merge="schema.fields"),
    Attack("changed-covered-witness", "accepted", ("drop.mismatch", "drop.mismatch"), False, merge="merge.unsigned-id"),
    Attack("unused-context-entry", "context.unused", merge="context.unused"),
    Attack("unused-config", "multisig-configs.unused", merge="multisig-configs.unused"),
    Attack("template-fourth-field", "template.form", merge="template.form"),
    Attack("duplicate-out-point", "transaction.duplicate-input", merge="transaction.duplicate-input"),
    Attack("conflicting-carried-entry", "accepted", (), True, "base", "merge.carried-conflict"),
    Attack("configs-for-no-input", "multisig-configs.unused", merge="multisig-configs.unused"),
    Attack("single-key-args-32", "lock.single-key-args"),
    Attack("token-consumed", "accepted", (), False, warnings=("type-leaves",)),
    Attack("since-rejected-by-lock", "accepted", (), False, merge="merge.unsigned-id", warnings=("since-rejected",)),
)


def _hex_add(h: str, n: int) -> str:
    return hex(int(h, 16) + n)


def apply(value: dict, change: dict) -> dict:
    """The base file's parsed value with the attack's change made."""
    v = copy.deepcopy(value)
    tx = v["transaction"]
    kind = change["kind"]
    if kind == "raise-input-capacity":
        op = tx["inputs"][change["input"]]["previous_output"]
        out = v["context"][op["tx_hash"]]["outputs"][int(op["index"], 16)]
        out["capacity"] = _hex_add(out["capacity"], int(change["add"], 16))
    elif kind == "set-output-lock":
        tx["outputs"][change["output"]]["lock"] = change["lock"]
    elif kind == "lower-output-capacity":
        out = tx["outputs"][change["output"]]
        out["capacity"] = _hex_add(out["capacity"], -int(change["by"], 16))
    elif kind == "add-signatures":
        for e in change["entries"]:
            v["signatures"].setdefault(e["group"], {})[e["signer"]] = e["signature"]
    elif kind == "set-signatures":
        v["signatures"][change["group"]] = change["entries"]
    elif kind == "replace-config-member":
        v["multisig_configs"][change["config"]]["public_key_hashes"][change["member"]] = change["key_hash"]
    elif kind == "add-field":
        v[change["name"]] = change["value"]
    elif kind == "append-witness":
        tx["witnesses"].append(change["witness"])
    elif kind == "add-context":
        v["context"][change["hash"]] = change["transaction"]
    elif kind == "add-configs":
        v["multisig_configs"].update(change["configs"])
    elif kind == "set-witness":
        tx["witnesses"][change["index"]] = change["witness"]
    elif kind == "duplicate-input":
        tx["inputs"].append(copy.deepcopy(tx["inputs"][change["input"]]))
        tx["witnesses"].append("0x")
    elif kind == "set-since":
        tx["inputs"][change["input"]]["since"] = change["since"]
    else:
        raise ValueError(f"unknown change {kind!r}")
    return v


def _merge(files: list[bytes], development_chain: bool) -> dict:
    try:
        out = merge.merge(files, development_chain)
    except merge.MergeRefused as e:
        return {"outcome": "refused", "check": e.check_id}
    return {"outcome": "merged", "sha256": cases.sha256(out), "_bytes": out}


def build(
    attack: Attack, input_bytes: bytes, base_vectors: dict[str, dict[str, bytes]], base_chains: dict[str, str]
) -> dict[str, bytes]:
    inp = canonical.check(input_bytes)
    base_id = inp.get("base")
    if base_id is not None:
        base = base_vectors[base_id]
        development_chain = base_chains[base_id] == "devnet"
        source_file = base["merged.json" if inp["from"] == "merged" else "file.json"]
        data = canonical.encode(apply(canonical.decode(source_file), inp["change"]))
    else:
        base = None
        development_chain = inp["chain"] == "devnet"
        data = cases.encode(cases.with_signatures(cases.sheet_from_input(inp), cases.recorded_signatures(inp)))
    files = {"input.json": input_bytes, "attack.json": data}
    result = cases.outcome_of(data, development_chain)
    expected = {"id": attack.id, "source": inp["source"], "base": base_id, "outcome": result["outcome"]}
    problems = []
    if result["outcome"] == "refused":
        expected["check"] = result["check"]
        if attack.outcome != result["check"]:
            problems.append(f"refused with {result['check']}")
    else:
        accepted, verified = result.pop("_accepted"), result.pop("_verified")
        final = cases.final_transaction(accepted, verified)
        expected["messages"] = {
            fmt_bytes(h): fmt_bytes(message(accepted, g)) for h, g in accepted.groups.items() if g.kind is not None
        }
        expected.update({k: result[k] for k in ("dropped", "normalized", "ready", "shown")})
        expected["final"] = None if final is None else {"sha256": cases.sha256(final[0]), "partial": final[1]}
        if attack.outcome != "accepted":
            problems.append("accepted")
        if tuple(sorted(d["reason"] for d in result["dropped"])) != tuple(sorted(attack.dropped)):
            problems.append(f"dropped {[d['reason'] for d in result['dropped']]}")
        if attack.ready is not None and result["ready"] != attack.ready:
            problems.append(f"ready {result['ready']}")
        if attack.final == "base" and (final is None or final[0] != base.get("final-tx.json")):
            problems.append("its final transaction isn't the base's")
        found = {w["id"] for w in result["shown"]["warnings"]}
        if not set(attack.warnings) <= found:
            problems.append(f"warnings {sorted(found)}")
    if base is not None:
        orders = [
            _merge([base["merged.json"], data], development_chain),
            _merge([data, base["merged.json"]], development_chain),
        ]
        if orders[0].get("sha256") != orders[1].get("sha256") or orders[0]["outcome"] != orders[1]["outcome"]:
            problems.append("the two merge orders differ")
        merged = orders[0]
        out = merged.pop("_bytes", None)
        orders[1].pop("_bytes", None)
        if merged["outcome"] == "merged":
            merged["equals_base_merged"] = out == base["merged.json"]
        expected["merge_with_base"] = merged
        want = attack.merge
        if want == "base" and not merged.get("equals_base_merged"):
            problems.append("the merge with the base isn't the base's merged file")
        if want not in (None, "base") and merged.get("check") != want:
            problems.append(f"merge {merged}")
    if problems:
        raise cases.VectorMismatch(f"{attack.id}: " + "; ".join(problems))
    expected["files"] = {name: cases.sha256(b) for name, b in sorted(files.items())}
    files["expected.json"] = canonical.encode(expected)
    return files
