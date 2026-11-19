"""The fee a signer is shown: inputs minus outputs, with each Nervos DAO withdrawing input at its amount.

In a DAO withdrawal the outputs may exceed the inputs' capacities (RFC 0023 L44), so each withdrawing input counts at
its maximum withdraw (`ckb.dao`). The deposit header comes from the input's witness; the withdrawing header only from
a verified inclusion proof of the input's previous transaction. With proofs for every withdrawing input the fee is
exact. Without one, the input counts at the largest amount any carried header other than its deposit header allows,
so the fee shown is an upper bound ("at most") and never lower than the real one: the withdrawing header is a header
dep of the transaction, and the accumulated rate never falls. When the DAO script would reject an input (no deposit
header it can read, a deposit number that doesn't match, a withdrawing header that isn't later), no fee is shown.
"""

from dataclasses import dataclass

from ..ckb import dao
from .reader import Accepted


@dataclass(frozen=True, slots=True)
class DaoInput:
    index: int
    deposit_header: bytes | None
    withdraw_header: bytes | None
    amount: int | None
    exact: bool
    minimal_since: int | None
    problem: str | None


@dataclass(frozen=True, slots=True)
class Fee:
    kind: str
    shannons: int | None
    dao_inputs: tuple[DaoInput, ...]


def _dao_input(accepted: Accepted, i: int, deposit_number: int) -> DaoInput:
    sheet = accepted.sheet
    tx = sheet.transaction
    output, data = accepted.spent[i]
    index = dao.deposit_header_index(tx.witnesses[i]) if i < len(tx.witnesses) else None
    if index is None or index >= len(tx.raw.header_deps):
        return DaoInput(i, None, None, None, False, None, "no deposit header the DAO script can read")
    dep_hash = tx.raw.header_deps[index]
    deposit = sheet.headers[dep_hash]
    if deposit.number != deposit_number:
        return DaoInput(i, dep_hash, None, None, False, None, "the deposit header's number isn't the cell's")
    proof = sheet.inclusion_proofs.get(tx.raw.inputs[i].previous_output.tx_hash)
    if proof is not None:
        withdraw = sheet.headers[proof.block_hash]
        since = dao.minimal_since(deposit, withdraw)
        if since is None:
            return DaoInput(i, dep_hash, proof.block_hash, None, False, None, "the withdrawing header isn't later")
        amount = dao.maximum_withdraw(output, data, deposit, withdraw)
        return DaoInput(i, dep_hash, proof.block_hash, amount, True, since, None)
    others = [h for k, h in sheet.headers.items() if k != dep_hash]
    if not others:
        return DaoInput(i, dep_hash, None, None, False, None, "no header that could be the withdrawing one")
    best = max(others, key=dao.accumulated_rate)
    return DaoInput(i, dep_hash, None, dao.maximum_withdraw(output, data, deposit, best), False, None, None)


def fee(accepted: Accepted) -> Fee:
    total_in = 0
    dao_inputs = []
    for i, (output, data) in enumerate(accepted.spent):
        n = dao.withdrawing_deposit_number(output, data)
        if n is None:
            total_in += output.capacity
            continue
        d = _dao_input(accepted, i, n)
        dao_inputs.append(d)
        total_in += d.amount or 0
    total_out = sum(o.capacity for o in accepted.sheet.transaction.raw.outputs)
    if any(d.amount is None for d in dao_inputs):
        return Fee("none", None, tuple(dao_inputs))
    kind = "exact" if all(d.exact for d in dao_inputs) else "at most"
    return Fee(kind, total_in - total_out, tuple(dao_inputs))
