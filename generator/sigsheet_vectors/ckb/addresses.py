"""Full-format CKB addresses: `0x00 || code_hash || hash_type || args`, Bech32m, with no length limit.

RFC 0021 L25-L36, L97, L108
(https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0021-ckb-address-format/0021-ckb-address-format.md):
the human-readable part is "ckb" on mainnet and "ckt" on testnet. Bech32m's checksum: BIP-350 L38-L61
(https://github.com/bitcoin/bips/blob/a7f91321f25b5be8d93e901775621c21519e80b7/bip-0350.mediawiki#L38-L61).
"""

from .molecule import HASH_TYPE_NAMES, HASH_TYPES, Script

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32M_CONST = 0x2BC830A3
GENERATOR = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
PREFIX = {"mainnet": "ckb", "testnet": "ckt"}


def _polymod(values: list[int]) -> int:
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= GENERATOR[i] if (top >> i) & 1 else 0
    return chk


def _hrp_expand(hrp: str) -> list[int]:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _convert_bits(data, from_bits: int, to_bits: int, pad: bool) -> list[int] | None:
    acc = bits = 0
    out = []
    maxv = (1 << to_bits) - 1
    for value in data:
        acc = (acc << from_bits) | value
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            out.append((acc >> bits) & maxv)
    if pad:
        if bits:
            out.append((acc << (to_bits - bits)) & maxv)
    elif bits >= from_bits or (acc << (to_bits - bits)) & maxv:
        return None
    return out


def encode(script: Script, network: str) -> str:
    hrp = PREFIX[network]
    payload = b"\x00" + script.code_hash + bytes([HASH_TYPES[script.hash_type]]) + script.args
    data = _convert_bits(payload, 8, 5, True)
    polymod = _polymod([*_hrp_expand(hrp), *data, 0, 0, 0, 0, 0, 0]) ^ BECH32M_CONST
    checksum = [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(CHARSET[d] for d in data + checksum)


def decode(address: str) -> tuple[str, Script]:
    """The network and the script of a full-format address; ValueError for anything else."""
    if address.lower() != address or "1" not in address:
        raise ValueError("not a lowercase Bech32m string")
    hrp, _, rest = address.rpartition("1")
    network = next((n for n, p in PREFIX.items() if p == hrp), None)
    if network is None or len(rest) < 6 or any(ch not in CHARSET for ch in rest):
        raise ValueError("not a CKB address")
    values = [CHARSET.index(ch) for ch in rest]
    if _polymod(_hrp_expand(hrp) + values) != BECH32M_CONST:
        raise ValueError("bad Bech32m checksum")
    payload = _convert_bits(values[:-6], 5, 8, False)
    if payload is None or len(payload) < 34 or payload[0] != 0 or payload[33] not in HASH_TYPE_NAMES:
        raise ValueError("not a full-format address")
    return network, Script(bytes(payload[1:33]), HASH_TYPE_NAMES[payload[33]], bytes(payload[34:]))
