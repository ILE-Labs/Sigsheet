"""The lock kinds version 1 signs, the known token scripts, and the cell deps that tell the network.

Version 1 recognizes a lock only by the input cell's code hash and hash type. Code hashes and cell deps:
RFC 0024 (https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0024-ckb-genesis-script-list/0024-ckb-genesis-script-list.md)
and CCC's tables at 7095cca (https://github.com/ckb-devrel/ccc/blob/7095ccad564b94ea2e59284cb4a364aa3499252e/packages/core/src/client/clientPublicMainnet.advanced.ts
and clientPublicTestnet.advanced.ts in the same folder). Token amounts: RFC 0025 L105-L128 (sUDT) and RFC 0052
L328-L370 (xUDT), a little-endian u128 at the start of the cell data.
"""

from .molecule import CellDep, OutPoint, Script

SINGLE_KEY = "single-key"
MULTISIG_GENESIS = "multisig-genesis"
MULTISIG_2024 = "multisig-2024"
MULTISIG_V2 = "multisig-v2"
MULTISIG_KINDS = (MULTISIG_GENESIS, MULTISIG_2024, MULTISIG_V2)


def _h(x: str) -> bytes:
    return bytes.fromhex(x)


SINGLE_KEY_CODE_HASH = _h("9bd7e06f3ecf4be0f2fcd2188b23f1b9fcc88e5d4b65a8637b17723bbda3cce8")
GENESIS_CODE_HASH = _h("5c5069eb0857efc65e1bca0c07df34c31663b3622fd3876c876320fc9634e2a8")
V2_CODE_HASH = _h("36c971b8d41fbd94aabca77dc75e826729ac98447b46f91e00796155dddb0d29")

# (code hash, hash type) -> kind, for mainnet and testnet. The single-key and genesis locks have the same code hash
# on both; the 2024 deployment has one per network; v2's `data1` code hash is its binary's hash.
LOCK_KINDS = {
    (SINGLE_KEY_CODE_HASH, "type"): SINGLE_KEY,
    (GENESIS_CODE_HASH, "type"): MULTISIG_GENESIS,
    (_h("d1a9f877aed3f5e07cb9c52b61ab96d06f250ae6883cc7f0a2423db0976fc821"), "type"): MULTISIG_2024,
    (_h("765b3ed6ae264b335d07e73ac332bf2c0f38f8d3340ed521cb447b4c42dd5f09"), "type"): MULTISIG_2024,
    (V2_CODE_HASH, "data1"): MULTISIG_V2,
}

# The local development chain the recorded vectors come from (ckb 0.210.0) deploys the 2024 binary under its own type
# id, so its code hash is that chain's alone. A reader accepts it only when told to, for those vectors.
DEVELOPMENT_CHAIN_LOCK_KINDS = {
    (_h("6283a479a3cf5d4276cd93594de9f1827ab9b55c7b05b3d28e4c2e0a696cfefd"), "type"): MULTISIG_2024,
}

TOKENS = {
    (_h("5e7a36a77e68eecc013dfa2fe6a23f3b6c344b04005808694ae6dd45eea4cfd5"), "type"): "sUDT",
    (_h("c5e5dcf215925f7ef4dfaf5f4b4f105bc321c02776d6e7d52a1db3fcd9d011a4"), "type"): "sUDT",
    (_h("50bd8d6680b8b9cf98b73f3c08faf8b2a21914311954118ad6609be6e78a1b95"), "data1"): "xUDT",
    (_h("25c29dc317811a6f6f3985a7a9ebc4838bd388d19d0feeecf0bcd60f6c0975bb"), "type"): "xUDT",
}


def _dep(tx_hash: str, index: int, dep_type: str) -> CellDep:
    return CellDep(OutPoint(_h(tx_hash), index), dep_type)


# The cell deps of the known scripts on each network: the lock dep groups, the DAO code cell, the token code cells.
KNOWN_CELL_DEPS = {
    "mainnet": frozenset(
        {
            _dep("71a7ba8fc96349fea0ed3a5c47992e3b4084b031a42264a018e0072e8172e46c", 0, "dep_group"),
            _dep("71a7ba8fc96349fea0ed3a5c47992e3b4084b031a42264a018e0072e8172e46c", 1, "dep_group"),
            _dep("44be4f4feda80c0e41783ab10e191df3b2bb5c3731b0970c916dbec385dcdc60", 0, "dep_group"),
            _dep("6888aa39ab30c570c2c30d9d5684d3769bf77265a7973211a3c087fe8efbf738", 0, "dep_group"),
            _dep("e2fb199810d49a4d8beec56718ba2593b665db9d52299a0f9e6e75416d73ff5c", 2, "code"),
            _dep("c7813f6a415144643970c2e88e0bb6ca6a8edc5dd7c1022746f628284a9936d5", 0, "code"),
            _dep("c07844ce21b38e4b071dd0e1ee3b0e27afd8d7532491327f39b786343f558ab7", 0, "code"),
        }
    ),
    "testnet": frozenset(
        {
            _dep("f8de3bb47d055cdf460d93a2a6e1b05f7432f9777c8c474abf4eec1d4aee5d37", 0, "dep_group"),
            _dep("f8de3bb47d055cdf460d93a2a6e1b05f7432f9777c8c474abf4eec1d4aee5d37", 1, "dep_group"),
            _dep("f2013f123b2cb745e3fdf5c935a3925647496f88090503eef58332a9245b4172", 0, "dep_group"),
            _dep("2eefdeb21f3a3edf697c28a52601b4419806ed60bb427420455cc29a090b26d5", 0, "dep_group"),
            _dep("8f8c79eb6671709633fe6a46de93c0fedc9c1b8a6527a18d3983879542635c9f", 2, "code"),
            _dep("e12877ebd2c3c364dc46c5c992bcfaf4fee33fa13eebdf82c591fc9825aab769", 0, "code"),
            _dep("bf6fb538763efec2a70a6a3dcb7242787087e1030c4e7d86585bc63a9d337f5f", 0, "code"),
        }
    ),
}


def lock_kind(lock: Script, development_chain: bool = False) -> str | None:
    """The kind of a lock version 1 signs, or None for a lock it carries."""
    key = (lock.code_hash, lock.hash_type)
    kind = LOCK_KINDS.get(key)
    if kind is None and development_chain:
        kind = DEVELOPMENT_CHAIN_LOCK_KINDS.get(key)
    return kind


def token_kind(type_script: Script | None) -> str | None:
    if type_script is None:
        return None
    return TOKENS.get((type_script.code_hash, type_script.hash_type))


def network(cell_deps: tuple[CellDep, ...]) -> str:
    """ "mainnet" or "testnet" when the cell deps include known ones of that network only, otherwise "unknown"."""
    found = {name for name, deps in KNOWN_CELL_DEPS.items() if any(d in deps for d in cell_deps)}
    return found.pop() if len(found) == 1 else "unknown"
