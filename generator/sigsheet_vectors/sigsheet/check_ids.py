"""Every check id and drop-reason id of the specification, in the specification's order. The spec's annex lists the
same ids; the reader reports the first refusal by its id and each dropped signature by a reason id."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Check:
    id: str
    rule: str
    needs_node: bool = False
    reason: str = ""


# Reader checks, run in this order; the first that fails refuses the file.
READER_CHECKS = (
    Check(
        "canonical.json",
        "The file is ASCII text holding one JSON value in the domain: no fraction or exponent, no NaN or Infinity, "
        "no repeated key, integers below 2^53.",
    ),
    Check("canonical.form", "Re-encoding the parsed value by RFC 8785 gives exactly the file's bytes."),
    Check("schema.fields", "The file is an object with exactly the seven fields."),
    Check("schema.version", '`version` is "0x1".'),
    Check(
        "schema.transaction",
        "`transaction` is a transaction in CKB RPC JSON with exactly its seven fields and the hex rules.",
    ),
    Check("schema.context", "`context` maps 32-byte hashes to raw transactions with exactly their six fields."),
    Check("schema.headers", "`headers` maps 32-byte hashes to headers with exactly their eleven fields."),
    Check("schema.inclusion-proofs", "`inclusion_proofs` maps 32-byte hashes to transaction proofs."),
    Check(
        "schema.multisig-configs",
        "`multisig_configs` maps 20-byte keys to configs whose R and M are integers from 0 to 255.",
    ),
    Check(
        "schema.signatures",
        "`signatures` maps 32-byte lock hashes to non-empty maps of 20-byte signers to 65-byte signatures.",
    ),
    Check("transaction.outputs-data", "`outputs` and `outputs_data` have the same length."),
    Check("transaction.duplicate-input", "No out point appears twice among the inputs."),
    Check("context.hash", "Every context entry hashes to its key."),
    Check(
        "context.missing", "Every input's previous transaction is in the context, with an output at the input's index."
    ),
    Check("context.unused", "Every context entry is a previous transaction of some input."),
    Check("headers.hash", "Every header hashes to its key."),
    Check("headers.missing", "Every header dep has its header."),
    Check("headers.unused", "Every header is a header dep."),
    Check("lock.single-key-args", "A single-key lock's args are 20 bytes."),
    Check("lock.multisig-args", "A multisig lock's args are 20 or 28 bytes."),
    Check("multisig-configs.values", "Each config has 1 to 255 members, 1 <= M <= N and R <= M."),
    Check("multisig-configs.repeated-key", "No config lists a member twice."),
    Check("multisig-configs.hash", "Each config's key is blake160 of its multisig script."),
    Check("multisig-configs.unused", "Each config's key occurs in the lock args of some input."),
    Check("multisig-configs.missing", "Every multisig group has the config its args name."),
    Check("template.missing", "The first input of every group of a kind version 1 signs has a witness."),
    Check(
        "template.form",
        "That witness is `0x`, or a three-field WitnessArgs that re-encodes to itself, with no lock, and with an "
        "`input_type` or an `output_type`.",
    ),
    Check("inclusion-proofs.target", "Each proof's key is the previous transaction of a Nervos DAO withdrawing input."),
    Check("inclusion-proofs.header", "Each proof's block hash is a carried header."),
    Check("inclusion-proofs.verify", "Each proof verifies against that header's transactions root."),
    Check("signatures.carried-limit", "A group of a kind the reader carries has at most 255 signatures."),
)

# Reasons a reader drops a signature from an accepted file, checked in this order for each entry.
DROP_REASONS = (
    Check("drop.no-group", "The entry is filed under a lock hash that is no lock group of the transaction."),
    Check("drop.not-member", "The filed signer isn't a member of the group; checked before any key recovery."),
    Check("drop.invalid", "The 65 bytes aren't a signature a key can be recovered from."),
    Check("drop.mismatch", "The signature recovers, over the group's message, to a key other than the filed signer."),
)

# Merge refuses files that the reader refuses (with that file's check id), and these.
MERGE_CHECKS = (
    Check("merge.unsigned-id", "Every file has the same unsigned id."),
    Check("merge.carried-conflict", "No signer has two different entries in a group of a kind the reader carries."),
)

# The checks no file can settle; each runs when the transaction is created or sent.
NODE_CHECKS = (
    Check(
        "node.unspent",
        "Every input is still unspent.",
        True,
        "Only the chain knows whether an out point has been spent.",
    ),
    Check(
        "node.scripts",
        "The cell deps resolve and every type script passes.",
        True,
        "The scripts run against the live cells and their own code.",
    ),
    Check(
        "node.network",
        "For a `data1` lock whose code cell the wallet doesn't know, the inputs are on the wallet's network.",
        True,
        "The file names no network, and a `data1` code hash is the same on every chain.",
    ),
    Check(
        "node.genesis",
        "For a genesis multisig group with N > 10, the finalized set passes `test_tx_pool_accept` before sending.",
        True,
        "The genesis binary rejects some valid sets, and their pattern is measured only up to N = 24.",
    ),
)

ALL = READER_CHECKS + DROP_REASONS + MERGE_CHECKS + NODE_CHECKS
IDS = {c.id: c for c in ALL}
