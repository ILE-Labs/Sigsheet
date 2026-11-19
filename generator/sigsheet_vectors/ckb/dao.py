"""Nervos DAO: telling its cells apart, the deposit header index, the maximum withdraw and the minimal since.

Every rule is the DAO script's own, at ckb-system-scripts 72eb92f
(https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c):
- a cell under the DAO type script has 8 bytes of data: 0 for a deposited cell, otherwise the deposit block number of
  a withdrawing cell (L425-L450); the type script's args are empty (L557);
- a withdrawing input's deposit header is `header_deps[i]`, where i is the first byte of the input's witness
  `input_type`, which must be exactly 8 bytes; RFC 0023 L76 describes a 64-bit integer, but the script reads only its
  first byte (L63-L98);
- the deposit header's number must equal the cell's deposit block number (L192), and the withdrawing header is the
  block that holds the withdrawing cell, which the script loads by the input itself (L197);
- the amount is occupied + (capacity - occupied) * AR_withdraw / AR_deposit, in integer division (L284-L316), with
  AR the u64 at bytes 8-16 of the header's `dao` field;
- the minimal since is an absolute epoch: the deposit epoch number plus the deposited epochs rounded up to whole
  180-epoch periods, with the deposit's index and length (L203-L259).
"""

from .molecule import CellOutput, Header, MoleculeError, Script, decode_witness_args

DAO_CODE_HASH = bytes.fromhex("82d76d1b75fe2fd9a27dfbaa65a039221a380d76c926f378d3f81cf3e7e13f2e")
DAO_TYPE = Script(DAO_CODE_HASH, "type", b"")
LOCK_PERIOD_EPOCHS = 180
SHANNONS_PER_BYTE = 100_000_000


def is_dao_cell(output: CellOutput) -> bool:
    return output.type == DAO_TYPE


def withdrawing_deposit_number(output: CellOutput, data: bytes) -> int | None:
    """The deposit block number a withdrawing cell holds, or None for any other cell."""
    if not is_dao_cell(output) or len(data) != 8:
        return None
    n = int.from_bytes(data, "little")
    return n if n > 0 else None


def deposit_header_index(witness: bytes) -> int | None:
    """The first byte of the witness's 8-byte `input_type`, or None when the script couldn't read one."""
    try:
        args = decode_witness_args(witness)
    except MoleculeError:
        return None
    if args.input_type is None or len(args.input_type) != 8:
        return None
    return args.input_type[0]


def accumulated_rate(header: Header) -> int:
    return int.from_bytes(header.dao[8:16], "little")


def occupied_capacity(output: CellOutput, data_length: int) -> int:
    """8 bytes of capacity, each script's 32 + 1 + args bytes, and the data, in shannons."""

    def script_bytes(s: Script | None) -> int:
        return 0 if s is None else 32 + 1 + len(s.args)

    return (8 + script_bytes(output.lock) + script_bytes(output.type) + data_length) * SHANNONS_PER_BYTE


def maximum_withdraw(output: CellOutput, data: bytes, deposit: Header, withdraw: Header) -> int:
    occupied = occupied_capacity(output, len(data))
    return occupied + (output.capacity - occupied) * accumulated_rate(withdraw) // accumulated_rate(deposit)


def epoch_parts(epoch: int) -> tuple[int, int, int]:
    """Epoch number (bits 0-23), index (bits 24-39) and length (bits 40-55)."""
    return epoch & 0xFFFFFF, (epoch >> 24) & 0xFFFF, (epoch >> 40) & 0xFFFF


def minimal_since(deposit: Header, withdraw: Header) -> int | None:
    """The earliest since the script accepts for the withdrawing input, or None if the withdrawing header isn't after
    the deposit header."""
    dn, di, dl = epoch_parts(deposit.epoch)
    wn, wi, wl = epoch_parts(withdraw.epoch)
    withdraw_fraction, deposit_fraction = wi * dl, di * wl
    if wn < dn or (wn == dn and withdraw_fraction <= deposit_fraction):
        return None
    deposited = wn - dn + (1 if withdraw_fraction > deposit_fraction else 0)
    lock_epochs = (deposited + LOCK_PERIOD_EPOCHS - 1) // LOCK_PERIOD_EPOCHS * LOCK_PERIOD_EPOCHS
    return (0x20 << 56) | (dn + lock_epochs) | (di << 24) | (dl << 40)
