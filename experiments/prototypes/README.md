# Prototypes: paths C, B and A (throwaway, design-stage)

Experiment code, not a spec and not a reference implementation. Python standard library only, on X1's independent implementation of CKB's encodings, hashes and secp256k1 ([`../X1/scripts/ckbcore.py`](../X1/scripts/ckbcore.py)). Experiments X2 to X7, XRT and XRTb run these, and so does the benchmark runner ([`../../bench/`](../../bench/README.md)).

| File | What it is |
|---|---|
| `core.py` | The model all three formats carry, and the rules every format follows: inputs resolved from the carried previous transactions (checked by hash); the lock kind taken from the input cell's code hash and hash type; the lock's message rule; verification; the merge (verified member signatures keyed by signer, low-s, the smaller bytes on a conflict) and finalize (the first R, then the lowest member indices up to M, in member order); the lock's rules run in Python on a final transaction |
| `fmt_c.py` | Path C, with D merged ([paths.md](../../paths.md#c-extend-the-json-that-ckb-cli-and-neuron-already-write-chosen)) |
| `fmt_b.py` | Path B as designed, and "B+w", B plus the witness templates |
| `fmt_a.py` | Path A's building-packet profile, Molecule as the canonical form, plus A's 1:1 JSON view |
| `mol.py` | Molecule decoding (strict) and the CKB types in RPC JSON form |
| `record.py` | Records which fields of a decoded file a computation reads (X2's boundary check) |
| `cases.py` | Builds every case's model from the case's own files ([X2](../X2/README.md)) |
| `devnet.py` | Devnet helpers for X3, X4, X5 and XQ14: RPC, funding from the miner key, sending |

## Choices the prototypes make, and why

| Choice | Why | Evidence |
|---|---|---|
| **Witness templates.** The file's transaction keeps every witness, but the first witness of each lock group the file signs has no lock field (`0x` when nothing else is in it). The message builds the zeroed lock from the config | The lock's message covers the group's other witnesses, the first witness's `input_type` and `output_type`, and every witness beyond the inputs ([background §1](../../background.md#1-the-multisig-lock)), so the file must carry them. Building the lock from the config keeps one source of the multisig script | [X2](../X2/results.md): B without witnesses fails S9 |
| **C keys `signatures` by the lock script hash**, not by lock args | Two lock groups can share args: the same multisig script under two deployments, or 20-byte and 28-byte args with the same script hash. Each group has its own message, so their signatures must be kept apart | [X3](../X3/results.md), case S10 |
| **C's `multisig_configs` has no `since`** | The since is in the 28-byte lock args, which the signer reads from the input cell; a config keyed by the 20-byte script hash can't hold two since values | [X3](../X3/results.md), case S11 |
| **Previous transactions carry no witnesses** (all formats) | The hash covers the raw transaction only, so the raw part proves an input ([background §2](../../background.md#2-transaction-structure-and-hash)); it saves 460 bytes for PR #34 | [X2a](../X2a/results.md) |
| **C's `context` is a map keyed by transaction hash** | No duplicates, a deterministic order, and each entry is checked against its key | [X2](../X2/results.md): C carries PR #34's previous transaction once; B twice |
| **Single-key inputs are signed in the same file.** C and B keep their signatures in the signature maps; A in the payload's witness, since the building-packet profile has actions only for multisig | PR #34 has a single-key input next to the multisig one; without it, someone would still collect that signature separately (G2) | [X2](../X2/results.md): R1, S7 |
| **A's previous transactions go in the first action only** | Carrying them in every multisig group's action would repeat them | [X2](../X2/results.md): S6 |
| **A's `change_output` must be None and `message` empty** | An unsigned `message` is a spoofing surface; `change_output` has no counterpart in C, so a packet with it isn't in the profile that maps onto C | [X2](../X2/results.md), the C4 mapping |
| **B's partial signatures sit on the first input of each group; its config on every multisig input** | B gives both per input; a CKB signature covers the whole group | [X2](../X2/results.md): B's bytes |
| **Every file must be complete** (every previous transaction and every multisig config it needs) | Then all files for one transaction carry the same context, and merging only unions signatures; C2 asks for checks from the file alone | [X3](../X3/results.md) |
| **Canonical form is enforced on decoding** (re-encoding must give the same bytes) | One byte string per content, so files can be compared and hashed: RFC 8785 for C and B, Molecule for A | [X2](../X2/results.md): 12 of 12 canonical in every format |

The rules added after the attacks considered in [the design record, section 5](../../design-record.md#5-security-analysis) (inclusion proofs, token display, refusing conflicting entries and others) are written as candidate rules in the scripts of [XRT](../XRT/README.md) and [XRTb](../XRTb/README.md); the prototypes here are the first version, unchanged.
