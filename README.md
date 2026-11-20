# Sigsheet

[![checks](https://github.com/ILE-Labs/Sigsheet/actions/workflows/checks.yml/badge.svg)](https://github.com/ILE-Labs/Sigsheet/actions/workflows/checks.yml)

**One file for signing a CKB multisig transaction: with the wallet each signer already uses, in any order, with no one collecting the signatures.**

A Sigsheet is one canonical JSON file per transaction. It carries:
- the transaction;
- the previous transaction of every input;
- the multisig configs;
- every signature so far, keyed by lock group and signer.

Each signer checks the file offline, adds a signature and passes the file on, or shares a copy. Anyone can merge copies: any order gives the same bytes. Anyone can finalize the transaction once enough members have signed.

> **Status: v0.1 in progress.**
> - **Published:** the [specification draft](spec/sigsheet.md) (version 0.1) and its [test vectors](vectors/), checked on Linux, macOS and Windows.
> - **Next:** a TypeScript library on CCC, ckb-cli commands and Neuron support (see the [roadmap](#roadmap)).
> - **Not yet:** no wallet release reads Sigsheet files.

## Contents

- [Why Sigsheet](#why-sigsheet)
- [How it works](#how-it-works)
- [The file](#the-file)
- [What a reader checks](#what-a-reader-checks)
- [Supported locks](#supported-locks)
- [Getting started](#getting-started)
- [Implementing Sigsheet](#implementing-sigsheet)
- [Repository layout](#repository-layout)
- [Roadmap](#roadmap)
- [Design and research](#design-and-research)
- [Contributing](#contributing)
- [License](#license)

## Why Sigsheet

A CKB multisig transaction is usually signed by several people, often with different tools: ckb-cli, Neuron or an app built on CCC. Today two things make that hard.

- **Each tool passes a partly signed transaction in its own form.** ckb-cli has its `tx` file, and Neuron has its offline-signing export. Signatures made in one tool don't move to another without conversion, so one person usually collects them and builds the final transaction.
- **A signature doesn't cover the input cells.** The multisig lock's message covers the transaction hash and the witnesses. The transaction hash covers each input's out point, not the cell it points to. So a signer who can't check the input cells can't check the amounts or the fee they're signing.

Sigsheet answers both:
- **One format for every tool.** Each wallet reads the same file, checks it, and adds its own signature with its own signer.
- **No collector.** Signatures are added and merged in any order, by anyone holding a copy.
- **Checkable offline.** The file carries every previous transaction, each checked by hash against its out point, so a reader can check every input cell without trusting a node.
- **Existing multisig.** It works with the multisig lock scripts and addresses already on chain. There's no new on-chain script.

## How it works

1. **Create.** A tool builds the transaction and fetches from a node what a signer needs: each input's previous transaction, plus, for a Nervos DAO withdrawal, the block headers and inclusion proofs. It writes the file with no signatures. Creating and sending are the only two steps that need a node.
2. **Sign.** Each signer's wallet reads the file and runs every check offline. It shows what the transaction does, then adds the signer's signature under its lock group.
3. **Share and merge.** The file moves from signer to signer, or each signer shares a copy in a chat, an email or a pull request, and anyone merges the copies. Merging verifies every signature and keeps the valid ones. Any order and any grouping give the same bytes.
4. **Finalize and send.** Once each lock group has enough valid signatures, anyone finalizes the file: it writes each group's witness and gives the final transaction. Sending it to a node is the last step.

## The file

A Sigsheet file is one JSON object with exactly seven fields ([spec §2](spec/sigsheet.md#2-the-file)):

| Field | Holds |
|---|---|
| `version` | `"0x1"` |
| `transaction` | The transaction in CKB RPC JSON. The first witness of each group to be signed is a template, without its signatures |
| `context` | The previous transaction of every input, keyed by its hash: the raw transaction, without witnesses |
| `headers` | A block header for every header dep, keyed by its block hash |
| `inclusion_proofs` | For a Nervos DAO withdrawal, the proofs that its previous transactions are in their blocks |
| `multisig_configs` | Each multisig config (members, `require_first_n`, `threshold`), keyed by the blake160 of its multisig script |
| `signatures` | `{lock script hash: {signer key hash: 65-byte signature}}` |

The file is canonical: RFC 8785 JSON in ASCII, with keys sorted, no whitespace, lowercase hex and no trailing newline. One content therefore has exactly one byte string, so files can be compared, hashed and merged byte for byte ([spec §3](spec/sigsheet.md#3-the-canonical-form)).

This is a 2-of-3 genesis multisig payment with both signatures in place, abridged and indented for reading (from [`vectors/cases/S1-genesis-2of3/merged.json`](vectors/cases/S1-genesis-2of3/merged.json)):

```json
{
  "context": {
    "0xb44ae96554e4ac61f367b5f06ba36e31d3bfd1428545af18cff43db712268635": {
      "cell_deps": [ … ], "header_deps": [], "inputs": [ … ],
      "outputs": [ { "capacity": "0x174876e800", "lock": { "args": "0x593b2fc5…a135", "code_hash": "0x5c5069eb…e2a8", "hash_type": "type" }, "type": null }, … ],
      "outputs_data": [ "0x", … ],
      "version": "0x0"
    }
  },
  "headers": {},
  "inclusion_proofs": {},
  "multisig_configs": {
    "0x593b2fc595771b0c3ebb9449e902f59e54afa135": {
      "public_key_hashes": [ "0xdf2c77f1…d5fe", "0x89918910…a3fe", "0x1e0ed48e…e53f" ],
      "require_first_n": 0,
      "threshold": 2
    }
  },
  "signatures": {
    "0x798b44900407ab4b90d6c804f2003f2f4c3df0990f876fd69ca72996becf171a": {
      "0x8991891046f102aba641db60e599d998e244a3fe": "0x05b6717c…1201",
      "0xdf2c77f15e45838f3983399fb63c7b5c576ad5fe": "0xb6ad649c…0601"
    }
  },
  "transaction": {
    "cell_deps": [ … ], "header_deps": [],
    "inputs": [ { "previous_output": { "index": "0x0", "tx_hash": "0xb44ae965…8635" }, "since": "0x0" } ],
    "outputs": [ … ], "outputs_data": [ "0x", "0x" ],
    "version": "0x0",
    "witnesses": [ "0x" ]
  },
  "version": "0x1"
}
```

## What a reader checks

A reader refuses a file at the first check that fails, and names that check's id ([spec §5](spec/sigsheet.md#5-reading-a-file-the-checks)).
- **31 reader checks,** all run offline from the file alone. Among them:
  - the canonical form, checked first;
  - every previous transaction hashes to the out point it proves;
  - every header and inclusion proof verifies;
  - every config hashes to its key and belongs to an input's lock;
  - no input is listed twice;
  - every template has its exact form.
- **Signatures** ([spec §7](spec/sigsheet.md#7-signatures)):
  - Membership is checked before any key recovery.
  - Each kept signature is normalized to low-s.
  - A signature that fails is dropped and named with a reason; it is never a reason to refuse the file.
- **What a signer is shown** is derived from the checked file only, never from a label the file declares ([spec §9](spec/sigsheet.md#9-what-a-signer-is-shown)):
  - every input and output;
  - the fee;
  - each lock group, its members and who has signed;
  - known tokens (sUDT, xUDT) moving in and out;
  - warnings, for example a `since` the lock will reject.
- **The Nervos DAO fee:** for a withdrawal, the specification counts each withdrawing input at its maximum withdraw. The fee is exact when it is computed from inclusion proofs, and an upper bound without them ([spec §9.2](spec/sigsheet.md#92-the-fee-and-nervos-dao-withdrawals)).
- **Four checks need a node,** and run when a transaction is created or sent ([spec §10](spec/sigsheet.md#10-creating-and-sending-the-steps-that-need-a-node)):
  - the inputs are unspent;
  - the cell deps resolve and every type script passes;
  - for a `data1` lock whose code cell the wallet doesn't know, the inputs are on the wallet's network;
  - for a genesis multisig with more than 10 members, the finalized set passes the node's `test_tx_pool_accept`.

The [security considerations](spec/sigsheet.md#13-security-considerations) list each attack considered, what stops it, and the vector that tests it.

## Supported locks

Version 1 signs these locks. It identifies each from the spent cell's code hash and hash type, never from a field of the file ([spec §6](spec/sigsheet.md#6-the-lock-kinds-and-their-messages)):

| Lock | Hash type | Networks |
|---|---|---|
| Single-key (`secp256k1_blake160_sighash_all`) | `type` | mainnet and testnet |
| Multisig, genesis deployment | `type` | mainnet and testnet |
| Multisig, 2024 deployment | `type` | mainnet and testnet (a different code hash on each) |
| Multisig v2 | `data1` | mainnet and testnet |

A transaction may also spend from other locks, such as Omnilock. Version 1 carries those groups and their signatures unchanged, and when it finalizes it leaves their witnesses for their own signers ([spec §8.3](spec/sigsheet.md#83-finalize)).

The genesis multisig binary rejects some valid signature sets. Finalizing picks a set the binary accepts, and the specification states the rule ([spec §8.2](spec/sigsheet.md#82-ready)).

## Getting started

Sigsheet isn't in any wallet release yet. What you can use today:
- the specification;
- the test vectors;
- the tools that build and check them.

### Read the specification

[`spec/sigsheet.md`](spec/sigsheet.md) is the draft of version 0.1. Every rule links to its evidence: the design record, an RFC, or upstream code at a pinned commit.

### Check the test vectors

You need Git and Python 3.14 (CI uses 3.14.4). The generator uses the standard library only.

```sh
git clone https://github.com/ILE-Labs/Sigsheet.git
cd Sigsheet
PYTHONPATH=generator python3 -m sigsheet_vectors check            # rebuild every vector in memory and compare every byte
PYTHONPATH=generator python3 -m unittest discover -s generator/tests
```

In Windows PowerShell, set the variable once, then run the same commands with `python`:

```powershell
$env:PYTHONPATH = "generator"
python -m sigsheet_vectors check
```

`check` passes when every committed vector rebuilds byte for byte from its recorded input. Two more commands:
- `build` rewrites the vectors.
- `fetch-mainnet` fetches the two mainnet cases read-only (from `https://mainnet.ckb.dev/` and GitHub, at pinned versions), rebuilds them under `vectors/mainnet/.fetched/` and checks every hash.

See [`generator/README.md`](generator/README.md) for both.

### Run the independent check

[`check/`](check/) confirms every vector with code that isn't the generator's:
- every group's message, computed by CCC's and ckb-cli's own code;
- every signature, recovered to the member it is filed under;
- every final transaction, run through the deployed lock binaries under ckb-debugger, with negative controls that must fail as the chain does.

You need Node 22, Rust 1.100 and ckb-debugger v1.1.1. The commands are in [`check/README.md`](check/README.md).

## Implementing Sigsheet

To add Sigsheet to a wallet or a tool:
1. **Implement the specification:** read, check, show, sign, merge and finalize, and optionally create and send.
2. **Run your implementation against every vector in [`vectors/`](vectors/).** It passes when it gives every result there, byte for byte wherever the result is a file.
3. **Report the check ids and drop-reason ids** that the specification defines ([Annex C](spec/sigsheet.md#annex-c-informative-the-check-ids)). The vectors name them.

The vectors (see [`vectors/README.md`](vectors/README.md)):

| Kind | How many | What each one holds |
|---|---|---|
| Cases (`vectors/cases/`) | 24 | The recorded input, the file as created, one copy per signature, the merged file, the final transaction, and `expected.json`: the outcome, the unsigned id, every group's message, what a signer is shown and the SHA-256 of every file |
| Attacks (`vectors/attacks/`) | 18 | The attack file and its expected result: refused with a check id, or accepted with named signatures dropped, plus the result of merging it with the honest file |
| Mainnet (`vectors/mainnet/`) | 2 | Only expected values and digests; `fetch-mainnet` rebuilds the files |

The cases cover all three multisig deployments, `require_first_n`, a `since` in the lock args, two groups, multisig with single-key, a Neuron export, extra witnesses, Nervos DAO withdrawals with and without proofs, creation from a node's answers, locks version 1 doesn't sign, and genesis multisig positions. The vectors' sources:
- the recorded cases come from a local development chain;
- the two mainnet vectors come from mainnet;
- the six synthetic cases were signed once, with keys held only in memory.

No private key is in the repository.

## Repository layout

| Path | What it is |
|---|---|
| [`spec/`](spec/) | The specification |
| [`vectors/`](vectors/) | The test vectors, at their exact bytes. Don't edit or reformat them; the generator writes them |
| [`generator/`](generator/) | The vector generator: Python 3, standard library only, separate from every implementation |
| [`check/`](check/) | The independent check: CCC, ckb-cli's and ckb-sdk's code, and the deployed lock binaries under ckb-debugger |
| [`.github/workflows/`](.github/workflows/) | The checks, run on every pull request and every push to `main` on Linux, macOS and Windows: read-only, with every action pinned by commit SHA |

## Roadmap

Each version is tracked as milestones in this repository.

| Milestone | Delivers | State |
|---|---|---|
| [v0.1 · Week 1](https://github.com/ILE-Labs/Sigsheet/milestone/1) | Specification draft and test vectors | Merged in [#48](https://github.com/ILE-Labs/Sigsheet/pull/48) |
| [v0.1 · Week 2](https://github.com/ILE-Labs/Sigsheet/milestone/2) | The TypeScript reference implementation on CCC | Next |
| [v0.1 · Week 3](https://github.com/ILE-Labs/Sigsheet/milestone/3) | ckb-cli commands in Rust | Planned |
| [v0.1 · Week 4](https://github.com/ILE-Labs/Sigsheet/milestone/4) | Neuron, and a demo on testnet | Planned |
| [v0.1 · Week 5](https://github.com/ILE-Labs/Sigsheet/milestone/5) | Specification v0.1, pull requests to the upstream projects, and the v0.1.0 release | Planned |
| [v0.2](https://github.com/ILE-Labs/Sigsheet/milestone/6) | Neuron's screens, more locks and more ways to move a file | Later |
| [v1.0](https://github.com/ILE-Labs/Sigsheet/milestone/7) | A stable standard, with a conformance suite and a CKB RFC | Later |

## Design and research

The [`research`](https://github.com/ILE-Labs/Sigsheet/tree/research) branch holds the design record behind Sigsheet. It covers:
- the problem;
- every design decision, with its evidence;
- the paths considered, and why each was dropped;
- the security analysis;
- the experiments and benchmarks that measured the design.

It also has a runner that re-runs the design-stage benchmarks on your machine: `./bench/run.sh`, Python 3, offline.

The branch is never merged into `main`, and its numbers are labelled design-stage.

A file without Nervos DAO data or carried locks maps losslessly onto a profile of CoBuild's building packet ([spec Annex A](spec/sigsheet.md#annex-a-informative-the-cobuild-profile)). Sigsheet complements CKB IDL instead of duplicating it ([spec Annex B](spec/sigsheet.md#annex-b-informative-the-boundary-with-ckb-idl)).

## Contributing

Questions and reports about real multisig workflows are the most useful contributions right now. Feedback on the specification draft is welcome in the issues. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

Please don't report security issues in public issues. See the [security section of CONTRIBUTING.md](CONTRIBUTING.md#security).

## License

MIT. See [LICENSE](LICENSE).

Maintained by ILE Labs.
