"""What a signer is shown: data derived from the checked file only, never a label the file declares.

- The network: "mainnet" or "testnet" when the cell deps include known ones of that network only, else "unknown";
  each lock is shown as its script with its address, both forms labelled when the network is unknown.
- Every input and output with its capacity, lock, type script, and the hash and size of its data.
- An output with no type script and no data whose lock is an input's lock is "back to the lock of input i"; any other
  output is a payment.
- The amounts of known tokens (sUDT, xUDT) on each cell, and their totals in and out.
- The fee (`fee.py`).
- Each lock group: its kind, its members, who has signed and whether it is ready.
- Warnings: an input's type script that appears on no output (RFC 0022 L217: a type script runs when its cell is
  spent); a since the lock will reject, by each deployment's rule; a genesis group with N > 10, checked with a node
  when sent; a DAO input the DAO script will reject.

The since rule (https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/common.h#L91-L125):
the genesis and 2024 deployments always check the since, with 0 when the args are 20 bytes; v2 checks it only when
the args are 28 bytes (the last 8, little-endian). Every group input must then have the same flags byte and a value at
least the required one, compared as an epoch with a fraction when the flags byte is 0x20.
"""

from ..ckb import addresses, scripts
from ..ckb.dao import epoch_parts
from ..ckb.hashing import ckbhash
from ..ckb.molecule import Script, script_hash
from ..ckb.rpc_json import fmt_bytes, fmt_uint, script_to
from .fee import fee
from .finalize import status
from .reader import Accepted, Group
from .signatures import Verified


def since_accepted(required: int, since: int) -> bool:
    flags, value = required >> 56, required & ((1 << 56) - 1)
    input_flags, input_value = since >> 56, since & ((1 << 56) - 1)
    if input_flags != flags:
        return False
    if flags == 0x20:
        an, ai, al = epoch_parts(input_value)
        bn, bi, bl = epoch_parts(value)
        return an > bn or (an == bn and ai * bl >= bi * al)
    return input_value >= value


def required_since(group: Group) -> int | None:
    """The since the group's lock checks, or None when it checks none."""
    args = group.lock.args
    if group.kind in (scripts.MULTISIG_GENESIS, scripts.MULTISIG_2024):
        return int.from_bytes(args[20:], "little") if len(args) == 28 else 0
    if group.kind == scripts.MULTISIG_V2 and len(args) == 28:
        return int.from_bytes(args[20:], "little")
    return None


def _token(output, data: bytes) -> dict | None:
    kind = scripts.token_kind(output.type)
    if kind is None:
        return None
    amount = str(int.from_bytes(data[:16], "little")) if len(data) >= 16 else None
    return {"kind": kind, "type_hash": fmt_bytes(script_hash(output.type)), "amount": amount}


def _lock(script: Script, network: str) -> dict:
    names = ("mainnet", "testnet") if network == "unknown" else (network,)
    return {"script": script_to(script), "addresses": {n: addresses.encode(script, n) for n in names}}


def _cell(index: int, output, data: bytes, network: str) -> dict:
    return {
        "index": index,
        "capacity": str(output.capacity),
        "lock": _lock(output.lock, network),
        "type": None if output.type is None else script_to(output.type),
        "data_hash": fmt_bytes(ckbhash(data)),
        "data_bytes": len(data),
        "token": _token(output, data),
    }


def _group_view(group: Group, st, verified: Verified) -> dict:
    if group.kind is None:
        return {
            "lock_hash": fmt_bytes(group.lock_hash),
            "kind": "carried",
            "code_hash": fmt_bytes(group.lock.code_hash),
            "hash_type": group.lock.hash_type,
            "inputs": list(group.inputs),
            "entries": len(verified.carried.get(group.lock_hash, {})),
        }
    view = {"lock_hash": fmt_bytes(group.lock_hash), "kind": group.kind, "inputs": list(group.inputs)}
    if group.kind == scripts.SINGLE_KEY:
        view["members"] = [fmt_bytes(group.lock.args)]
    else:
        c = group.config
        view["members"] = [fmt_bytes(k) for k in c.public_key_hashes]
        view["require_first_n"] = c.require_first_n
        view["threshold"] = c.threshold
    view["signed"] = list(st.signed)
    view["ready"] = st.ready
    return view


def view(accepted: Accepted, verified: Verified) -> dict:
    raw = accepted.sheet.transaction.raw
    network = scripts.network(raw.cell_deps)
    inputs = [_cell(i, o, d, network) for i, (o, d) in enumerate(accepted.spent)]
    input_locks = [o.lock for o, _ in accepted.spent]
    outputs = []
    for j, (o, d) in enumerate(zip(raw.outputs, raw.outputs_data, strict=True)):
        cell = _cell(j, o, d, network)
        plain = o.type is None and d == b""
        cell["label"] = (
            f"back to the lock of input {input_locks.index(o.lock)}" if plain and o.lock in input_locks else "payment"
        )
        outputs.append(cell)

    totals: dict[str, dict] = {}
    for side, cells in (("in", inputs), ("out", outputs)):
        for cell in cells:
            t = cell["token"]
            if t is None or t["amount"] is None:
                continue
            entry = totals.setdefault(
                t["type_hash"], {"kind": t["kind"], "type_hash": t["type_hash"], "in": 0, "out": 0}
            )
            entry[side] += int(t["amount"])
    tokens = [{**e, "in": str(e["in"]), "out": str(e["out"])} for _, e in sorted(totals.items())]

    f = fee(accepted)
    fee_view = {
        "kind": f.kind,
        "shannons": None if f.shannons is None else str(f.shannons),
        "dao_inputs": [
            {
                "input": d.index,
                "deposit_header": None if d.deposit_header is None else fmt_bytes(d.deposit_header),
                "withdraw_header": None if d.withdraw_header is None else fmt_bytes(d.withdraw_header),
                "amount": None if d.amount is None else str(d.amount),
                "exact": d.exact,
                "minimal_since": None if d.minimal_since is None else fmt_uint(d.minimal_since),
            }
            for d in f.dao_inputs
        ],
    }

    warnings = []
    output_types = [o.type for o in raw.outputs]
    for i, (o, _) in enumerate(accepted.spent):
        if o.type is not None and o.type not in output_types:
            warnings.append(
                {
                    "id": "type-leaves",
                    "input": i,
                    "type_hash": fmt_bytes(script_hash(o.type)),
                    "token": inputs[i]["token"],
                }
            )
    sts = status(accepted, verified)
    for h, group in accepted.groups.items():
        required = required_since(group)
        if required is not None:
            for i in group.inputs:
                since = raw.inputs[i].since
                if not since_accepted(required, since):
                    warnings.append(
                        {"id": "since-rejected", "group": fmt_bytes(h), "input": i, "since": fmt_uint(since)}
                    )
        if group.kind == scripts.MULTISIG_GENESIS and len(group.config.public_key_hashes) > 10:
            warnings.append({"id": "genesis-node-check", "group": fmt_bytes(h)})
    for d in f.dao_inputs:
        if d.problem:
            warnings.append({"id": "dao-rejected", "input": d.index, "reason": d.problem})

    return {
        "network": network,
        "inputs": inputs,
        "outputs": outputs,
        "tokens": tokens,
        "fee": fee_view,
        "groups": [_group_view(g, sts[h], verified) for h, g in accepted.groups.items()],
        "warnings": warnings,
    }
