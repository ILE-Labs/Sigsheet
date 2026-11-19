"""Creating a file: the one step besides sending that needs a node.

From a built transaction (with its witness templates) and the node's answers: `get_transaction` for each input's
previous transaction, kept without witnesses or hash; `get_header` for each header dep; and `get_transaction_proof`
for the previous transaction of each Nervos DAO withdrawing input, when the node gave one. The multisig configs come
from the creator's own records. Every transaction and header hash is recomputed; the inclusion proofs are verified
when the reader checks the created file. The result has no signatures. This module reads recorded answers only; it
never calls a node.
"""

from ..ckb import dao, rpc_json
from ..ckb.molecule import Transaction, transaction_hash
from .schema import MultisigConfig, Sheet


class CreateError(ValueError):
    pass


def _previous(node: dict, h: bytes):
    result = node.get("get_transaction", {}).get(rpc_json.fmt_bytes(h))
    if result is None:
        raise CreateError(f"the node data has no transaction 0x{h.hex()}")
    tx = dict(result["transaction"])
    if tx.pop("hash", None) != rpc_json.fmt_bytes(h):
        raise CreateError(f"the node's transaction 0x{h.hex()} has another hash field")
    raw = rpc_json.transaction_from(tx, "get_transaction").raw
    if transaction_hash(raw) != h:
        raise CreateError(f"the node's transaction 0x{h.hex()} doesn't hash to it")
    return raw


def create(transaction: Transaction, node: dict, configs: dict[bytes, MultisigConfig]) -> Sheet:
    context = {}
    for i in transaction.raw.inputs:
        h = i.previous_output.tx_hash
        if h not in context:
            context[h] = _previous(node, h)
    headers = {}
    for h in transaction.raw.header_deps:
        view = node.get("get_header", {}).get(rpc_json.fmt_bytes(h))
        if view is None:
            raise CreateError(f"the node data has no header 0x{h.hex()}")
        headers[h] = rpc_json.header_view_from(view, "get_header")
    proofs = {}
    for i in transaction.raw.inputs:
        op = i.previous_output
        prev = context[op.tx_hash]
        if dao.withdrawing_deposit_number(prev.outputs[op.index], prev.outputs_data[op.index]) is None:
            continue
        answer = node.get("get_transaction_proof", {}).get(rpc_json.fmt_bytes(op.tx_hash))
        if answer is not None:
            proofs[op.tx_hash] = rpc_json.proof_from(answer, "get_transaction_proof")
    return Sheet(transaction, context, headers, proofs, dict(configs), {})
