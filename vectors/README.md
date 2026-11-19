# Test vectors

The Sigsheet test vectors: each case and each attack of the specification (`spec/sigsheet.md`) as files at their
exact bytes, with the results a reader must give. An implementation passes when it gives every result here, byte for
byte where the result is a file.

Every `.json` file here is canonical JSON (RFC 8785, ASCII, no whitespace, no trailing newline) and is written only by
the generator (`generator/`). Don't edit or reformat any of them: a formatter changes the bytes the vectors are about.

## Rebuild and check

From the repository root:

```sh
PYTHONPATH=generator python -m sigsheet_vectors check           # rebuild in memory, compare every byte
PYTHONPATH=generator python -m sigsheet_vectors build           # rewrite every built file
PYTHONPATH=generator python -m sigsheet_vectors fetch-mainnet   # fetch R1 and R2 read-only and check them
```

`build` and `check` read only this folder. `index.json` lists every vector with its kind, its chain, the experiment
it comes from, and the SHA-256 of each of its files.

## A case: `cases/<id>/`

| File | What it holds |
|---|---|
| `input.json` | The recorded inputs: `transaction` (the built transaction with its witness templates), `multisig_configs`, then either the file's `context`, `headers` and `inclusion_proofs` as recorded, or `node`: the node's answers for creating the file (`get_transaction`, `get_header`, `get_transaction_proof` results); `signatures`, every recorded signature with the group and signer it is filed under; `recorded`, the results the experiments measured, which the vector must reproduce; `chain`; `source` |
| `file.json` | The file as created: no signatures |
| `partial/<nn>-<signer>.json` | One copy per recorded signature: the created file plus that one signature |
| `merged.json` | The merge of every partial file. Any order and grouping of the partial files merges to these bytes |
| `final-tx.json` | The final transaction in CKB RPC JSON, when every group of a kind version 1 signs is ready; partial when a carried lock is present |
| `expected.json` | The outcome (accepted, or refused with a check id); the unsigned id; the transaction hash; each group's message; the signatures a reader drops, with reason ids; whether the file is ready; `shown`, what a signer is shown; whether the final transaction is partial; the SHA-256 of every file above |

## An attack: `attacks/<id>/`

| File | What it holds |
|---|---|
| `input.json` | The honest base vector (`base`), which of its files the attack starts from (`from`: `merged` or `file`), and the change (`change`); or, for a synthetic attack, a whole input as in a case |
| `attack.json` | The attack file |
| `expected.json` | Refused with a check id, or accepted with the dropped signatures and their reason ids, its messages, whether it is ready and what a signer is shown; `final`, the SHA-256 of its final transaction; `merge_with_base`, the merge with the honest base's merged file in both orders: refused with a check id, or merged, with whether it equals the base's merged file |

## The mainnet cases: `mainnet/`

R1 and R2 are real mainnet transactions. No mainnet chain data is kept here: `mainnet/<id>/expected.json` holds only
the unsigned id, the messages, the outcome, the final transaction hash and the SHA-256 of every file the fetch rebuilds;
`mainnet/inputs.sha256` pins the GitHub files the fetch reads. `fetch-mainnet` writes the fetched files and the rebuilt
vector folders under `mainnet/.fetched/`, which git ignores.

## The development chain

The recorded vectors come from a local development chain (ckb 0.210.0) whose genesis holds the three multisig
deployments' binaries. The single-key, genesis multisig and v2 multisig locks have the same code hash there as on
mainnet and testnet. The 2024 deployment's binary sits under that chain's own type id, so its code hash there,
`0x6283a479a3cf5d4276cd93594de9f1827ab9b55c7b05b3d28e4c2e0a696cfefd` (`type`), is that chain's alone. A reader running
the vectors whose `chain` is `devnet` accepts this one extra code hash as the 2024 deployment; S2 needs it.

## Where each vector's inputs come from

| Vectors | Inputs |
|---|---|
| S1-S9, S4N | Recorded on a local development chain (ckb 0.210.0): the research branch's `experiments/X2/cases/<id>.json`, with the committed transactions of `experiments/X1/data/devnet/committed/` |
| S10, S11, R1-35 | Recorded on the same chain: the research branch's `experiments/X3/cases/<id>.json` |
| `dao-*` | Recorded on the same chain: the committed two-deposit Nervos DAO withdrawal and the node's answers for it (its two previous transactions, four headers and two transaction proofs); the research branch's `experiments/XRTb/results/dao-flow.json` records the same proofs and the node's fees. `dao-cut-output` is the never-committed variant with its output cut to the deposits, unsigned. `dao-proof-block-changed` has one proof's block hash changed to its deposit block's |
| `creation-c1` | Recorded on the same chain: a transaction created by ckb-cli and committed (the research branch's `experiments/XRT/results/creation.json`, flow C1), with the node's answer for its previous transaction |
| `unknown-lock-partial`, `omnilock-multisig-carried`, `genesis-*` | Synthetic: signatures and key hashes made once with keys made in memory and dropped (`generator/sigsheet_vectors/author.py`). The carried lock's code hash is ckbhash of the text "Sigsheet test vectors: a lock that version 1 doesn't sign", which no deployment has; the Omnilock code hash is mainnet's |
| `attacks/*` | Each changes a recorded or synthetic base; `single-key-args-32` and `token-consumed` are synthetic files. Random bytes and new signatures were made once, with the synthetic cases |
| R1 | Mainnet transaction `0x4396de69818bd88b7fce64797ccec25d1294912d56846432f29fd192120992ee`, replayed from fiber-scripts PR #34's deploy file at commit `026027f54f6a90cb48d8cc184b230e2018bb8611` and its four signature comments |
| R2 | Mainnet transaction `0x63a7f3a52fc91c52939186ca9c1064238ccdfe498d3398f25707537f591bbaa4`, a genesis 2-of-3 payment, and its previous transaction |

The experiments named in `index.json` (X2, X3, X4, XRT, XRTb) are described on this repository's `research` branch.
