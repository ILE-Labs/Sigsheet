"""The Sigsheet file: exactly seven top-level fields, each with its shape, to and from the parsed JSON value.

version           "0x1"
transaction       the transaction in CKB RPC JSON, with its witness templates
context           {transaction hash: raw previous transaction}
headers           {block hash: header}
inclusion_proofs  {transaction hash: transaction proof}
multisig_configs  {blake160(multisig script): {public_key_hashes, require_first_n, threshold}}
signatures        {lock script hash: {signer key hash: 65-byte signature}}
"""

from dataclasses import dataclass

from ..ckb import rpc_json
from ..ckb.hashing import blake160
from ..ckb.merkle import TransactionProof
from ..ckb.molecule import Header, RawTransaction, Transaction
from ..ckb.rpc_json import JsonShapeError, fmt_bytes, parse_bytes

VERSION = "0x1"
TOP_LEVEL = ("context", "headers", "inclusion_proofs", "multisig_configs", "signatures", "transaction", "version")
CONFIG_FIELDS = ("public_key_hashes", "require_first_n", "threshold")


class SchemaError(ValueError):
    def __init__(self, check_id: str, detail: str):
        super().__init__(detail)
        self.check_id = check_id


@dataclass(frozen=True, slots=True)
class MultisigConfig:
    require_first_n: int
    threshold: int
    public_key_hashes: tuple[bytes, ...]

    def script(self) -> bytes:
        """S || R || M || N || the N key hashes, with S = 0
        (https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c#L13-L28)."""
        n = len(self.public_key_hashes)
        return bytes([0, self.require_first_n, self.threshold, n]) + b"".join(self.public_key_hashes)

    def key(self) -> bytes:
        return blake160(self.script())


@dataclass(frozen=True, slots=True)
class Sheet:
    transaction: Transaction
    context: dict[bytes, RawTransaction]
    headers: dict[bytes, Header]
    inclusion_proofs: dict[bytes, TransactionProof]
    multisig_configs: dict[bytes, MultisigConfig]
    signatures: dict[bytes, dict[bytes, bytes]]


def _map(value, check_id: str, name: str, key_size: int, parse_value) -> dict:
    if not isinstance(value, dict):
        raise SchemaError(check_id, f"{name} must be an object")
    out = {}
    for k, v in value.items():
        try:
            out[parse_bytes(k, f"{name} key", key_size)] = parse_value(v, f"{name}[{k}]")
        except JsonShapeError as e:
            raise SchemaError(check_id, str(e)) from e
    return out


def config_from_json(v, path: str) -> MultisigConfig:
    v = rpc_json.expect_object(v, path, CONFIG_FIELDS)
    for f in ("require_first_n", "threshold"):
        if type(v[f]) is not int or not 0 <= v[f] <= 255:
            raise JsonShapeError(f"{path}.{f}", "must be an integer from 0 to 255")
    keys = rpc_json.expect_list(v["public_key_hashes"], f"{path}.public_key_hashes")
    hashes = tuple(parse_bytes(k, f"{path}.public_key_hashes[{i}]", 20) for i, k in enumerate(keys))
    return MultisigConfig(v["require_first_n"], v["threshold"], hashes)


def _signers(v, path: str) -> dict[bytes, bytes]:
    if not isinstance(v, dict) or not v:
        raise JsonShapeError(path, "must be a non-empty object")
    return {parse_bytes(k, f"{path} key", 20): parse_bytes(s, f"{path}[{k}]", 65) for k, s in v.items()}


def from_json(value) -> Sheet:
    if not isinstance(value, dict) or set(value) != set(TOP_LEVEL):
        raise SchemaError("schema.fields", f"the file must have exactly the fields {list(TOP_LEVEL)}")
    if value["version"] != VERSION:
        raise SchemaError("schema.version", f"version {value['version']!r} isn't {VERSION!r}")
    try:
        transaction = rpc_json.transaction_from(value["transaction"], "transaction")
    except JsonShapeError as e:
        raise SchemaError("schema.transaction", str(e)) from e
    return Sheet(
        transaction,
        _map(value["context"], "schema.context", "context", 32, rpc_json.raw_transaction_from),
        _map(value["headers"], "schema.headers", "headers", 32, rpc_json.header_from),
        _map(value["inclusion_proofs"], "schema.inclusion-proofs", "inclusion_proofs", 32, rpc_json.proof_from),
        _map(value["multisig_configs"], "schema.multisig-configs", "multisig_configs", 20, config_from_json),
        _map(value["signatures"], "schema.signatures", "signatures", 32, _signers),
    )


def config_to_json(c: MultisigConfig) -> dict:
    return {
        "public_key_hashes": [fmt_bytes(k) for k in c.public_key_hashes],
        "require_first_n": c.require_first_n,
        "threshold": c.threshold,
    }


def to_json(sheet: Sheet) -> dict:
    return {
        "version": VERSION,
        "transaction": rpc_json.transaction_to(sheet.transaction),
        "context": {fmt_bytes(h): rpc_json.raw_transaction_to(t) for h, t in sheet.context.items()},
        "headers": {fmt_bytes(h): rpc_json.header_to(x) for h, x in sheet.headers.items()},
        "inclusion_proofs": {fmt_bytes(h): rpc_json.proof_to(p) for h, p in sheet.inclusion_proofs.items()},
        "multisig_configs": {fmt_bytes(k): config_to_json(c) for k, c in sheet.multisig_configs.items()},
        "signatures": {
            fmt_bytes(g): {fmt_bytes(k): fmt_bytes(s) for k, s in entries.items()}
            for g, entries in sheet.signatures.items()
            if entries
        },
    }
