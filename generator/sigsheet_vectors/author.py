"""One-time authoring of the vector inputs that no recording holds.

The synthetic cases (a lock version 1 carries, an Omnilock multisig-mode group, the genesis positions) and the attack
inputs need new signatures, new key hashes or random bytes. This module makes them once: every key is made in memory
from `secrets`, used to sign, and dropped; only key hashes, signatures and bytes are written, into each vector's
`input.json`. It writes only the inputs that don't exist yet, so running it again changes nothing. Building and
checking the vectors never call it.

    python -m sigsheet_vectors.author
"""

import dataclasses
import pathlib
import secrets

from .ckb import rpc_json, scripts
from .ckb.hashing import blake160, ckbhash
from .ckb.molecule import Script, dynvec, encode_bytes, script_hash, transaction_hash
from .ckb.rpc_json import fmt_bytes, fmt_uint
from .ckb.secp256k1 import N, high_s_twin, public_key, sign
from .sigsheet import canonical, reader
from .sigsheet.messages import message
from .sigsheet.schema import MultisigConfig, config_to_json
from .vectors.cases import encode, sheet_from_input

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"
CKB = 100_000_000
SYNTHETIC = "synthetic; signatures and key hashes authored once with keys made in memory and dropped"
OMNILOCK_CODE_HASH = bytes.fromhex("9b819793a64463aed77c615d6cb226eea5487ccfc0783043a587254cda2b6f26")
XUDT_CODE_HASH = bytes.fromhex("50bd8d6680b8b9cf98b73f3c08faf8b2a21914311954118ad6609be6e78a1b95")
# A code hash no deployment has: ckbhash of this text, so its origin is plain.
CARRIED_CODE_HASH = ckbhash(b"Sigsheet test vectors: a lock that version 1 doesn't sign")


def _dep(tx_hash: str, index: int) -> dict:
    return {"out_point": {"tx_hash": tx_hash, "index": fmt_uint(index)}, "dep_type": "dep_group"}


SINGLE_KEY_DEPS = _dep("0x71a7ba8fc96349fea0ed3a5c47992e3b4084b031a42264a018e0072e8172e46c", 0)
GENESIS_DEPS = _dep("0x71a7ba8fc96349fea0ed3a5c47992e3b4084b031a42264a018e0072e8172e46c", 1)
V2_DEPS = _dep("0x6888aa39ab30c570c2c30d9d5684d3769bf77265a7973211a3c087fe8efbf738", 0)


class Key:
    """A secret made in memory; only its key hash leaves this module."""

    def __init__(self):
        while True:
            secret = secrets.token_bytes(32)
            if 0 < int.from_bytes(secret, "big") < N:
                break
        self._secret = secret
        self.hash = blake160(public_key(secret))

    def sign(self, msg: bytes) -> bytes:
        return sign(msg, self._secret)


def _script(code_hash: bytes, hash_type: str, args: bytes) -> dict:
    return rpc_json.script_to(Script(code_hash, hash_type, args))


def _multisig(kind_code: tuple[bytes, str], keys: list[Key], r: int, m: int) -> tuple[dict, MultisigConfig]:
    cfg = MultisigConfig(r, m, tuple(k.hash for k in keys))
    return _script(kind_code[0], kind_code[1], cfg.key()), cfg


def _cell(capacity: int, lock: dict, type_: dict | None = None) -> dict:
    return {"capacity": fmt_uint(capacity), "lock": lock, "type": type_}


def _synthetic(
    outputs_spent: list[tuple[dict, str]], outputs: list[dict], deps: list[dict], configs: list[MultisigConfig]
) -> dict:
    """An input with one synthetic previous transaction holding the spent cells, and a transaction spending them."""
    prev = {
        "version": "0x0",
        "cell_deps": [],
        "header_deps": [],
        "inputs": [
            {"since": "0x0", "previous_output": {"tx_hash": fmt_bytes(ckbhash(b"synthetic funding")), "index": "0x0"}}
        ],
        "outputs": [c for c, _ in outputs_spent],
        "outputs_data": [d for _, d in outputs_spent],
    }
    h = fmt_bytes(transaction_hash(rpc_json.raw_transaction_from(prev, "prev")))
    tx = {
        "version": "0x0",
        "cell_deps": deps,
        "header_deps": [],
        "inputs": [
            {"since": "0x0", "previous_output": {"tx_hash": h, "index": fmt_uint(i)}} for i in range(len(outputs_spent))
        ],
        "outputs": outputs,
        "outputs_data": ["0x"] * len(outputs),
        "witnesses": ["0x"] * len(outputs_spent),
    }
    return {
        "chain": "synthetic",
        "source": SYNTHETIC,
        "transaction": tx,
        "context": {h: prev},
        "headers": {},
        "inclusion_proofs": {},
        "multisig_configs": {fmt_bytes(c.key()): config_to_json(c) for c in configs},
        "signatures": [],
    }


def _accepted(inp: dict) -> reader.Accepted:
    return reader.read(encode(sheet_from_input(inp)), False)


def _sign(inp: dict, lock: dict, signers: list[Key], as_kind: str | None = None) -> list[dict]:
    """Signatures over the group's message, each filed under its key hash. `as_kind` signs a carried group's message
    by another kind's rule, to make a realistic 65-byte entry that the reader keeps unverified."""
    accepted = _accepted(inp)
    group = accepted.groups[bytes.fromhex(lock_hash(lock)[2:])]
    if as_kind is not None:
        group = dataclasses.replace(group, kind=as_kind)
    msg = message(accepted, group)
    return [
        {"group": lock_hash(lock), "signer": fmt_bytes(k.hash), "signature": fmt_bytes(k.sign(msg))} for k in signers
    ]


def lock_hash(lock: dict) -> str:
    return fmt_bytes(script_hash(rpc_json.script_from(lock, "lock")))


def unknown_lock_partial() -> dict:
    m = [Key() for _ in range(3)]
    other = Key()
    ms_lock, cfg = _multisig((scripts.V2_CODE_HASH, "data1"), m, 0, 2)
    carried = _script(CARRIED_CODE_HASH, "data1", other.hash)
    inp = _synthetic(
        [(_cell(1000 * CKB, ms_lock), "0x"), (_cell(500 * CKB, carried), "0x")],
        [_cell(1500 * CKB - 100_000, ms_lock)],
        [V2_DEPS],
        [cfg],
    )
    inp["signatures"] = _sign(inp, ms_lock, m[:2]) + _sign(inp, carried, [other], scripts.SINGLE_KEY)
    return inp


def omnilock_multisig_carried() -> dict:
    m = [Key() for _ in range(3)]
    o = [Key() for _ in range(3)]
    ms_lock, cfg = _multisig((scripts.V2_CODE_HASH, "data1"), m, 0, 2)
    omni_cfg = MultisigConfig(0, 2, tuple(k.hash for k in o))
    # Omnilock's args: a 21-byte identity (auth flag 0x06, the multisig mode, then the 20-byte config key) and the
    # omnilock flags byte 0x00 (https://github.com/nervosnetwork/omnilock/blob/280dd97ac0930ea1ed766a18d49478229347c832/c/omni_lock.c#L136-L140).
    omni = _script(OMNILOCK_CODE_HASH, "type", b"\x06" + omni_cfg.key() + b"\x00")
    inp = _synthetic(
        [(_cell(1000 * CKB, ms_lock), "0x"), (_cell(300 * CKB, omni), "0x")],
        [_cell(1300 * CKB - 100_000, ms_lock)],
        [V2_DEPS],
        [cfg, omni_cfg],
    )
    inp["signatures"] = _sign(inp, ms_lock, m[:2])
    return inp


def genesis(n: int, m: int, r: int, signers: list[int]) -> dict:
    keys = [Key() for _ in range(n)]
    lock, cfg = _multisig((scripts.GENESIS_CODE_HASH, "type"), keys, r, m)
    payee = _script(scripts.SINGLE_KEY_CODE_HASH, "type", Key().hash)
    inp = _synthetic([(_cell(1000 * CKB, lock), "0x")], [_cell(1000 * CKB - 100_000, payee)], [GENESIS_DEPS], [cfg])
    inp["signatures"] = _sign(inp, lock, [keys[i] for i in signers])
    return inp


def single_key_args_32() -> dict:
    k = Key()
    lock = _script(scripts.SINGLE_KEY_CODE_HASH, "type", k.hash + bytes(12))
    payee = _script(scripts.SINGLE_KEY_CODE_HASH, "type", k.hash)
    return _synthetic([(_cell(100 * CKB, lock), "0x")], [_cell(100 * CKB - 100_000, payee)], [SINGLE_KEY_DEPS], [])


def token_consumed() -> dict:
    m = [Key() for _ in range(3)]
    ms_lock, cfg = _multisig((scripts.V2_CODE_HASH, "data1"), m, 0, 2)
    token = _script(XUDT_CODE_HASH, "data1", b"\x11" * 32)
    amount = fmt_bytes((1_000_000).to_bytes(16, "little"))
    spent = [(_cell(1000 * CKB, ms_lock), "0x"), (_cell(200 * CKB, ms_lock, token), amount)]
    return _synthetic(spent, [_cell(1200 * CKB - 100_000, ms_lock)], [V2_DEPS], [cfg])


def _base(case: str, frm: str, change: dict, source: str) -> dict:
    return {"base": case, "from": frm, "change": change, "source": source}


def _junk_signature() -> str:
    """65 bytes a key can be recovered from (r and s below N, recovery id 0 or 1), from no member."""
    r = secrets.randbelow(N - 1) + 1
    s = secrets.randbelow(N - 1) + 1
    return fmt_bytes(r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([secrets.randbelow(2)]))


def _random_config() -> MultisigConfig:
    return MultisigConfig(0, 2, tuple(Key().hash for _ in range(3)))


def attack_inputs() -> dict[str, dict]:
    s1 = canonical.check((ROOT / "cases" / "S1-genesis-2of3" / "input.json").read_bytes())
    (group,) = {e["group"] for e in s1["signatures"]}
    sig = {e["signer"]: e["signature"] for e in s1["signatures"]}
    (cfg_key, cfg) = next(iter(s1["multisig_configs"].items()))
    members = cfg["public_key_hashes"]
    s10 = canonical.check((ROOT / "cases" / "S10-same-script-two-deployments" / "input.json").read_bytes())
    unused_h, unused_tx = next(iter(s10["context"].items()))
    outsider = Key()
    s1_accepted = _accepted(s1)
    s1_msg = message(s1_accepted, s1_accepted.groups[bytes.fromhex(group[2:])])
    twin = fmt_bytes(high_s_twin(bytes.fromhex(sig[members[0]][2:])))
    four_fields = fmt_bytes(dynvec([b"", encode_bytes(b"\x07"), b"", encode_bytes(b"\x01\x02")]))
    unknown = canonical.check((ROOT / "cases" / "unknown-lock-partial" / "input.json").read_bytes())
    carried = next(e for e in unknown["signatures"] if e["group"] != unknown["signatures"][0]["group"])
    cfg_unused = _random_config()
    omni_configs = [_random_config() for _ in range(3)]
    return {
        "falsified-input-cell": _base(
            "S1-genesis-2of3",
            "merged",
            {"kind": "raise-input-capacity", "input": 0, "add": fmt_uint(1_000_000 * CKB)},
            "X4 attack 1",
        ),
        "swapped-transaction": _base(
            "S1-genesis-2of3",
            "merged",
            {
                "kind": "set-output-lock",
                "output": 0,
                "lock": _script(scripts.SINGLE_KEY_CODE_HASH, "type", b"\xee" * 20),
            },
            "X4 attacks 2-3",
        ),
        "altered-output": _base(
            "S1-genesis-2of3",
            "merged",
            {"kind": "lower-output-capacity", "output": 1, "by": fmt_uint(100 * CKB)},
            "X4 attacks 2-3",
        ),
        "non-member-signature": _base(
            "S1-genesis-2of3",
            "merged",
            {
                "kind": "add-signatures",
                "entries": [
                    {"group": group, "signer": fmt_bytes(outsider.hash), "signature": fmt_bytes(outsider.sign(s1_msg))}
                ],
            },
            "X4 attack 4; XRT-2 F10",
        ),
        "junk-signatures": _base(
            "S1-genesis-2of3",
            "merged",
            {
                "kind": "set-signatures",
                "group": group,
                "entries": {
                    members[0]: twin,
                    members[1]: sig[members[1]],
                    members[2]: sig[members[1]],
                    fmt_bytes(secrets.token_bytes(20)): fmt_bytes(secrets.token_bytes(65)),
                },
            },
            "X4 attack 5",
        ),
        "many-junk-entries": _base(
            "S1-genesis-2of3",
            "merged",
            {
                "kind": "add-signatures",
                "entries": [
                    {"group": group, "signer": fmt_bytes(secrets.token_bytes(20)), "signature": _junk_signature()}
                    for _ in range(32)
                ],
            },
            "XRT-2 F09",
        ),
        "swapped-config": _base(
            "S1-genesis-2of3",
            "merged",
            {"kind": "replace-config-member", "config": cfg_key, "member": 0, "key_hash": fmt_bytes(b"\xee" * 20)},
            "X4 attack 7",
        ),
        "display-field": _base(
            "S1-genesis-2of3",
            "merged",
            {"kind": "add-field", "name": "description", "value": "routine payout, safe to sign"},
            "X4 attack 9",
        ),
        "changed-covered-witness": _base(
            "S1-genesis-2of3", "merged", {"kind": "append-witness", "witness": "0xdeadbeef"}, "X4 attack 10"
        ),
        "unused-context-entry": _base(
            "S1-genesis-2of3",
            "merged",
            {"kind": "add-context", "hash": unused_h, "transaction": unused_tx},
            "XRT-2 F03",
        ),
        "unused-config": _base(
            "S1-genesis-2of3",
            "merged",
            {"kind": "add-configs", "configs": {fmt_bytes(cfg_unused.key()): config_to_json(cfg_unused)}},
            "XRT-2 F03",
        ),
        "template-fourth-field": _base(
            "S1-genesis-2of3", "merged", {"kind": "set-witness", "index": 0, "witness": four_fields}, "XRT-2 L2"
        ),
        "duplicate-out-point": _base("S1-genesis-2of3", "merged", {"kind": "duplicate-input", "input": 0}, "XRT-2 L3"),
        "conflicting-carried-entry": _base(
            "unknown-lock-partial",
            "merged",
            {"kind": "set-signatures", "group": carried["group"], "entries": {carried["signer"]: fmt_bytes(bytes(65))}},
            "XRTb-2 F01",
        ),
        "configs-for-no-input": _base(
            "omnilock-multisig-carried",
            "merged",
            {"kind": "add-configs", "configs": {fmt_bytes(c.key()): config_to_json(c) for c in omni_configs}},
            "XRTb-2 F10",
        ),
        "single-key-args-32": {**single_key_args_32(), "base": None, "source": f"XRTb-2 F11; {SYNTHETIC}"},
        "token-consumed": {**token_consumed(), "base": None, "source": f"XRTb-2 F09; {SYNTHETIC}"},
        "since-rejected-by-lock": _base(
            "S1-genesis-2of3",
            "file",
            {"kind": "set-since", "input": 0, "since": fmt_uint(0x8000000000000001)},
            "XRT-3 C",
        ),
    }


def case_inputs() -> dict[str, dict]:
    return {
        "unknown-lock-partial": unknown_lock_partial(),
        "omnilock-multisig-carried": omnilock_multisig_carried(),
        "genesis-n12-m2-skip-10": genesis(12, 2, 0, [5, 10, 11]),
        "genesis-n12-m2-10-11-not-ready": genesis(12, 2, 0, [10, 11]),
        "genesis-n12-m11-r11": genesis(12, 11, 11, list(range(11))),
        "genesis-n20-m1-18-not-ready": genesis(20, 1, 0, [18]),
    }


def _write(path: pathlib.Path, value: dict) -> None:
    if path.exists():
        print(f"left as it is: {path.relative_to(ROOT.parent)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical.encode(value))
    print(f"wrote {path.relative_to(ROOT.parent)}")


def main() -> None:
    for case_id, inp in case_inputs().items():
        _write(ROOT / "cases" / case_id / "input.json", inp)
    for attack_id, inp in attack_inputs().items():
        _write(ROOT / "attacks" / attack_id / "input.json", inp)


if __name__ == "__main__":
    main()
