# Numbers

Every measured number, with its conditions and its source. **All of them are design-stage:** measured on throwaway prototypes ([`experiments/prototypes/`](experiments/prototypes/README.md)) and on patched copies of the wallets ([X6](experiments/X6/results.md)), not on phase 1's implementations. Phase 1's acceptance tests re-measure them ([design record §8.2](design-record.md#82-acceptance-tests)).

Conditions: November 2026, on one Linux machine (2 CPUs, 7.6 GB RAM). "Devnet" is a local CKB devnet (ckb 0.210.0) whose genesis holds all three multisig deployments' binaries as on mainnet ([X1](experiments/X1/README.md#environment-and-versions)). Fresh test keys only. No testnet or mainnet transaction was sent.

To re-run the ones that work offline and compare them with the values below: `./bench/run.sh` ([bench/README.md](bench/README.md)).

## Sizes of a Sigsheet file (X2, X7)

Bytes; zlib level 9 in brackets. Formats: C (JSON per lock group), B as designed (per input, no witnesses), B+w (B plus the witness templates), A (building-packet profile, Molecule), A's JSON view. Source: [X2 results](experiments/X2/results.md#2-bytes-zlib-level-9-in-brackets), `experiments/X2/results/x2.json`.

| Case | C | B | B+w | A | A JSON view |
|---|---:|---:|---:|---:|---:|
| R1 fiber-scripts PR #34 (mainnet) | 733,078 (247,785) | 1,300,648 (445,344) | 1,300,721 (445,366) | 367,378 (222,827) | 734,217 (248,461) |
| R2 genesis 2-of-3 payment (mainnet) | 2,371 (914) | 2,221 (865) | 2,278 (883) | 2,037 (1,136) | 3,458 (1,456) |
| S1 genesis 2-of-3 (devnet) | 4,653 (1,132) | 4,635 (1,154) | 4,692 (1,172) | 3,244 (1,389) | 5,862 (1,727) |
| S3 two inputs, one group | 4,788 (1,133) | 8,067 (1,211) | 8,140 (1,227) | 3,405 (1,396) | 6,205 (1,744) |
| S6 two multisig groups | 6,065 (1,506) | 9,010 (1,548) | 9,083 (1,567) | 4,786 (1,840) | 8,351 (2,243) |
| S7 multisig + single key | 5,377 (1,276) | 8,407 (1,324) | 8,480 (1,344) | 3,636 (1,513) | 6,712 (1,860) |

- One signature with the ids that place it (unsigned transaction id, lock group, signer), canonical JSON: 367 bytes in every case ([X7](experiments/X7/results.md#1-sizes-bytes)).
- The same data as binary and hex JSON ([X2a](experiments/X2a/results.md)): PR #34's transaction plus its proof, 366,357 bytes binary against 733,033 hex JSON; path A's duplicated cell data, 79,880 bytes. PR #34's deploy file: 904,588 bytes, 81.27% of it input transactions ([X1](experiments/X1/results.md#numbers)).

## Round trips, the mapping and the boundary (X2)

- Lossless and canonical: C 12 of 12, B 11 of 12 (fails S9, the witness beyond the inputs; 0 of 2 signatures verify), B+w 12 of 12, A 12 of 12. Signatures verified from the file alone: 32 of 32 (C, B+w, A), 30 of 32 (B).
- C → A → C and A → C → A byte-identical: 12 of 12 each way.
- Fields a signer's message computation reads: only the transaction, the previous transactions (with the spent outputs' lock code hash, hash type and args) and the multisig config, in every format and case.
- Two implementations of A (Python, and CCC's patch layer) give byte-identical packets: 12 of 12 ([X6](experiments/X6/results.md#4-what-path-a-adds-on-top-of-c-measured-in-ccc-and-how-b-compares)).

## Merging (X3, X3a)

- Same bytes from three merge orders (left fold, right fold, random tree), every trial: R1 50 of 50; S6, S7, S10, S11, R1-35 200 of 200 each; in C, B+w and A. Idempotent and junk-free in every trial ([X3](experiments/X3/results.md)).
- S10 (one script under genesis and v2): 6 signatures under one key if keyed by lock args, 3 and 3 if keyed by lock group.
- On PR #34's five real signatures ([X3a](experiments/X3a/results.md)): CCC's `aggregateTransactions` gave 60 different witnesses from five files in 120 orders; the design's rule agreed in 2,000 of 2,000 trials, BIP-174's first-seen in 1,285; PCZT's strict rule failed in 1,531.

## Attacks (X4)

- High-s twin accepted on chain by every deployment: genesis block 15,486 (`0xc2e31b41…`), 2024 block 15,489 (`0x0d20e97b…`), v2 block 15,493 (`0x30e59afd…`) ([X4](experiments/X4/results.md#1-the-lock-accepts-a-malleated-signature-on-all-three-deployments-run-on-chain)).
- Every attack caught in C, B+w and A; a CoBuild reader unaware of A's profile would show a fee of 1,000,000.00001186 CKB for a real fee of 0.00001186 CKB.
- Replay: a committed transaction resent, rejected (`TransactionFailedToResolve`); old signatures on a new transaction, rejected (lock error -52).

## End to end on the devnet (X5, X3, XQ14)

| Flow | Tools | Transaction | Block |
|---|---|---|---|
| X5 F1, 2-of-3 v2 passed along | ckb-cli, CCC | `0xe59840d5…8a8a` | 17,310 |
| X5 F2, 3-of-5 v2, four copies merged by three tools | ckb-cli, CCC, Neuron, Python | `0x0f44c2b2…28d2` | 17,335 |
| X5 F3, 2-of-3 genesis | Neuron, ckb-cli | `0x5f7c2bd6…b483` | 17,348 |
| X5 F4, a witness beyond the inputs | Neuron (patched), CCC | `0xf8fb2235…79af` | 17,366 |
| X5 F5, multisig + single key | ckb-cli, CCC, Neuron, Python merge | `0x66c2a43a…a9a1` | 17,384 |
| X5 F6, 3-of-5 with R = 1 | CCC, ckb-cli, Neuron | `0x2c2b5901…21c8` | 17,400 |
| X5 F7, 2024 deployment | CCC (ckb-cli adds nothing) | `0x9963afdf…96ae` | 17,410 |
| X3 S10, S11, R1-35 | prototypes | `0x0c18da2d…`, `0x7c0658fe…`, `0x39e18888…` | 19,045, 19,049, 19,053 |
| XQ14 genesis 2-of-3 with the emulated Ledger | Ledger (emulator), prototype | `0xa6d8a1ec…7dcd` | 15,689 |
| XQ14 two inputs, one group | Ledger (emulator), prototype | `0x7f91b994…f928` | 15,758 |
| XQ14 v2 via the blind message-hash path | Ledger (emulator), prototype | `0x25747c22…3720` | 15,806 |

Full hashes are in each experiment's results. X1 committed nine mixed-tool transactions (blocks 1,122-1,238, [X1](experiments/X1/results.md#devnet-transactions-all-committed)).

## Adoption (X6)

| Wallet (pinned) | Path C patch: files, lines added (code lines) | Own tests before → after |
|---|---|---|
| ckb-cli v2.0.0 `80efc21` | 3 files, +415 (381) | 7 passed → 7 passed |
| CCC 1.23.1 `7095cca` | 2 files, +260 (229) | 759 passed → 759 passed |
| Neuron v0.204.1 `d3a7467` | 2 files, +153 / −2 (137) | 103 passed, 24 failed (no SQLite) → the same |

- These are the design's first version. The rules added after the attacks considered (Nervos DAO inclusion proofs, token display, refusing conflicting entries) were tested on the prototypes only, so phase 1's patches will be larger.
- Path A on top of C in CCC: +103 lines (95 code). Rust Molecule code for CoBuild's types in cryptape's proof of concept: 5,200 generated lines. Prototype format layers: C 63, B 98, A 199 code lines on a shared core of 350; Molecule decoding 77 (B and A).
- Creating the file ([XRT-4](experiments/XRT/results.md#xrt-4-creating-the-file-inside-the-wallets)): ckb-cli +91 lines (87 code), its tests 7 of 7; CCC a 59-line module (52 code). CCC's file for ckb-cli's transaction: byte-identical (1,931 bytes).
- CKB IDL reuse: `ckb-idl-client` adds 29 crate versions to ckb-cli's graph (391 → 417) and `Cargo.lock` +401 / −31; the client is 1,318 Rust code lines; the N ≤ 5 IDL document is 18,372 bytes; no TypeScript client exists ([XC4](experiments/XC4/results.md)).

## Times (X7, X5)

Times are the measuring machine's; on your machine they will differ.

- Python prototypes (pure-Python secp256k1, so upper bounds): decode and validate 40 ms (the genesis 2-of-3 payment) to 136-146 ms (PR #34); merge two files 41 ms to 147-165 ms; finalize 20 ms to 65 ms.
- Patched wallets on PR #34 (733 KB), whole process: ckb-cli merge 0.10 s, finalize 0.08 s; CCC merge 1.86 s (614 ms in-module), finalize 1.84 s (618 ms).
- One signature, whole process (X5): ckb-cli 0.04-0.13 s; CCC about 2 s (122-229 ms in-module); Neuron 9-12 s under jest.

## Limits (X7)

- CKB tx pool: 512,000 bytes; PR #34's final transaction is 81,889 bytes.
- The lock's witness buffer: 32 KB; the largest multisig lock (N = M = 255): 21,679 bytes.
- Relay message limits seen (NIP-11 examples): 16,384, 65,535 and 524,288 bytes.

## The Ledger emulator (XQ14)

Nervos app 0.6.3 built for the Nano S Plus, Speculos 0.27.6, the emulator's default test seed ([XQ14](experiments/XQ14/results.md)).
- A 2-of-3 genesis payment with change back to the multisig: 11 screens, 10 right presses and 1 press of both; 3,200 bytes in 14 APDUs. The "Amount" screen showed 999 CKB for a 500 CKB payment (the multisig change is counted); the genesis 2-of-3 payment's replay showed 8,559,214 CKB for its 2,873,564 CKB payment.
- Previous transactions up to 1,000,460 bytes, sent once or twice (2,001,540 bytes, 8,703 APDUs): signed, and the signature verifies. PR #34 (649,900 bytes, 2,826 APDUs): refused (its lock and shape), and the app exits.
- Refused: v2 and 2024 locks, a multisig input next to another input, six or more outputs. Signed: a multisig it isn't a member of. Through "Allow sign hash" (off by default): a v2 lock message, shown only as hex.

## The genesis binary (XRT-1, XRTb-1)

- N 2-12 ([XRT-1](experiments/XRT/results.md#xrt-1-which-valid-signature-sets-each-deployed-binary-accepts)): genesis 1,047 of 1,297 sets accepted with R = 0 and 19 of 21 with R = 1; 2024 472 of 472; v2 460 of 460. Rule: a set fails exactly when position 10 signs and M ≤ 10 (1,318 of 1,318 genesis sets fit).
- N 13-24: genesis 397 of 423 in member order (position 10 with M ≤ 10; position 18 with M = 1) and 330 of 388 in descending order; v2 76 of 76.
- N = 12 ([XRTb-1](experiments/XRTb/results.md#xrtb-1-the-genesis-binary-with-a-required-member-and-a-set-no-order-fixes), `test_tx_pool_accept`): M = R = 11 with members 0-10, accepted in both orders; M = 2: {5, 10} and {10, 11} rejected in both orders, {5, 11} accepted.

## Prototype checks (XRT-2, XRTb-2)

- 20,000 junk signature entries (3.6 MB file): 106.49 s to read in the pure-Python prototype; 0.022 s with the membership check first ([XRT-2](experiments/XRT/results.md#xrt-2-prototype-checks-no-chain)).
- One out point listed twice: accepted by the prototype before the rule, with a fee shown 1,000.001 CKB.
- A conflict in a group the reader doesn't sign ([XRTb-2](experiments/XRTb/results.md#xrtb-2-the-simpler-rules-against-the-design-rules-offline)): under the "smaller bytes" rule, 65 zero bytes kept over a valid signature in 2 of 2 orders; the design's rule refuses the merge in 2 of 2 orders.
- 50 configs for no input: 2,685 bytes → 14,585 bytes, the unsigned id unchanged; without the rule all 52 configs are kept, with it 2.
- A single-key input with 32-byte args: accepted without the rule, its signature dropped.
- A 1,000,000-unit xUDT cell consumed with no token output: shown as "fee: 0.001 CKB" without the token rules.

## Devnet transactions after the attacks considered (XRT-3, XRT-4)

| Flow | Transaction | Block |
|---|---|---|
| Partial finalize, then the other lock's own signer | `0x0942c9cf…8984` | 50,247 |
| Another group's signature carried by a version 1 reader, finalized later | `0xe887f919…92f2` | 50,251 |
| ckb-cli creates (its own `tx` commands, then `tx sigsheet-new`), CCC and ckb-cli sign, ckb-cli sends | `0xbd095ca9…34e2` | 50,741 |
| CCC creates, ckb-cli and CCC sign, CCC sends | `0xf6f0ab8c…1dd9` | 50,749 |

## A Nervos DAO withdrawal of two deposits (XRTb-3)

Devnet with an epoch length of 10 blocks ([XRTb-3](experiments/XRTb/results.md#xrtb-3-a-nervos-dao-withdrawal-of-two-deposits)): deposits of 2,000 and 3,000 CKB (blocks 62,540, 62,543), phase 1 in blocks 62,546 and 63,546, phase 2 committed in block 64,357 (`0xcf852daf…8735`, 3,155,574 cycles), header deps [D1, D2, W1, W2].

| The fee shown (CKB) | The withdrawal sent | Its output cut to the deposits |
|---|---|---|
| the node (`test_tx_pool_accept`) | 0.001 | 7.12722788 |
| inputs − outputs | −7.12522788 | 0.001 |
| an upper bound from the other header deps | 4.63600414 | 11.76223202 |
| inclusion proofs (verified offline) | 0.001 | 7.12722788 |

Each input's withdrawable amount from the proofs equals the node's `calculate_dao_maximum_withdraw` (2,000.02791696 and 3,007.09831092 CKB). CKB's transaction proofs verify offline in a 2-transaction and a 5-transaction block (2 or 3 lemmas); a changed block hash or transaction hash fails.
