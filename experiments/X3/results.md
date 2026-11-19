# X3 results: merging in any order, any number of times, with junk

Conditions (design-stage): 2026-11-18 (UTC); the prototypes of C, B+w and A; six cases (R1 real; S6, S7 from X1; S10, S11, R1-35 new on the devnet); trial counts in `README.md`. Raw output: `results/x3.json`.

## 1. One result in any order, in every format

| Case | Trials | Same bytes from three merge orders (C / B+w / A) | Idempotent | No junk survives | Finalized when ready, lock rules pass |
|---|---:|---|---|---|---|
| R1 PR #34 (3-of-5 v2 + single key) | 50 | 50 / 50 / 50 | all | all | 20 / 29 / 24 of 20 / 29 / 24 ready |
| S6 two multisig groups | 200 | 200 / 200 / 200 | all | all | every ready trial (20 / 25 / 23) |
| S7 multisig + single key | 200 | 200 / 200 / 200 | all | all | every ready trial (74 / 75 / 80) |
| **S10** one script, genesis + v2 | 200 | 200 / 200 / 200 | all | all | every ready trial (74 / 90 / 87) |
| **S11** one script, 20- and 28-byte args | 200 | 200 / 200 / 200 | all | all | every ready trial (100 / 84 / 98) |
| **R1-35** 3-of-5, R = 1 | 200 | 200 / 200 / 200 | all | all | every ready trial (133 / 130 / 140) |

"Same bytes" compares whole encoded files: the merged file is identical whichever order and grouping the partial files are merged in, with the high-s twins, the second signatures by the same member, and the junk in the pool. A file for a different transaction is refused in every case.

**A can't hold a malformed entry at all:** its signature field is a fixed 85-byte struct, so the truncated 64-byte junk can't be written in an A file (2 pool entries per case; C and B carry them and the merge drops them).

## 2. Signatures must be keyed by lock group, not by lock args (S10)

S10 spends one cell of the multisig script [s1, s2, s3] under the genesis deployment and one under v2. The two lock groups have the **same lock args**, but different lock scripts, so each has its own message. Keyed by lock args (as ckb-cli's `tx` file keys `signatures`), the six signatures land under one key: 6 for a 2-of-3. Keyed by lock script hash (the prototypes' choice for C), they stay 3 and 3. ckb-cli's own `sign_inputs` keeps one signature per lock args in a map, so it would overwrite one group's signature with the other's ([`tx_helper.rs` L226-L294](https://github.com/nervosnetwork/ckb-cli/blob/80efc21c30e9fc7847407a217034681b6e46c763/src/utils/tx_helper.rs#L226-L294), read at `80efc21`). The finalized S10 transaction was committed (below).

## 3. First R (R1-35)

Without s1 (member 0, required), four members signed but the group isn't ready, and finalizing is refused ("needs the first 1 and 3 in all"). With all five, the finalizer picks members 0, 1, 2: the required one, then the lowest indices.

## 4. On the devnet

| Case | Transaction | Block |
|---|---|---|
| S10 (genesis + v2, same args) | `0x0c18da2db7569db58d7b5aecad54796f47c251b6fa5878cb18e0f258d4c75fe7` | 19,045 |
| S11 (20- and 28-byte args) | `0x7c0658fea5e89094a0fe7cc9e6473a0ef08c66e7430bc261ef49bfe4e1e4f5ce` | 19,049 |
| R1-35 (R = 1) | `0x39e188886a76739252aea02da07765c8375731e54278a2c245f864899a6bc0d9` | 19,053 |

## Answer

The merge rule gives byte-identical files in any order and grouping, is idempotent, drops every kind of junk, and normalizes malleated twins, in all three formats and on every case, including the two new edge cases. It needs the signatures keyed by lock group (lock script hash): keyed by lock args, two groups that share a multisig script under two deployments would mix their signatures.
