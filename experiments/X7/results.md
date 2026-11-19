# X7 results: sizes, times and limits

Conditions (design-stage): 2026-11-19 (UTC), on a Linux machine with 2 CPUs; the prototypes and the X6 patched wallets, offline. Raw output: `results/x7.json`; the sizes come from X2 (`../X2/results/x2.json`). Commands: `README.md`.

## 1. Sizes (bytes)

| Case | C | B+w | A | A's JSON view | One posted signature |
|---|---:|---:|---:|---:|---:|
| R1 PR #34 (real, 3-of-5 v2 + single key) | 733,078 | 1,300,721 | 367,378 | 734,217 | 367 |
| R2 genesis 2-of-3 payment (real) | 2,371 | 2,278 | 2,037 | 3,458 | 367 |
| S3 two inputs, one group | 4,788 | 8,140 | 3,405 | 6,205 | 367 |
| S6 two multisig groups | 6,065 | 9,083 | 4,786 | 8,351 | 367 |
| S7 multisig + single key | 5,377 | 8,480 | 3,636 | 6,712 | 367 |

Compressed (zlib 9), PR #34 is 247,785 (C), 445,366 (B+w) and 222,827 (A); the genesis 2-of-3 payment 914, 883 and 1,136. All cases: `../X2/results.md`.

## 2. Times

| Operation (median) | Python prototype, small case (R2) | Python, PR #34 | ckb-cli, PR #34 (whole process) | CCC, PR #34 (whole process; in-module) |
|---|---:|---:|---:|---:|
| Decode and validate (every signature verified) | 40 ms | 136-146 ms | | |
| Compute every group's message | 0.03 ms | 1.8 ms | | |
| Merge two partial files | 41 ms | 147-165 ms | **0.10 s** | **1.86 s; 614 ms** |
| Merge one file per signature (6 for PR #34) | 40 ms | 174-238 ms | | |
| Finalize | 20 ms | 65 ms | **0.08 s** | **1.84 s; 618 ms** |

Ranges are across the three formats (C, B+w, A), which differ little: the time goes into hashing the previous transactions and recovering keys, which every format must do. ckb-cli's and CCC's merges of the two PR #34 files are byte-identical, and the finalized transaction has the hash of the one committed on mainnet, `0x4396de69…92ee`, and passes the lock's rules.

## 3. Limits

| Limit | Value | Against the cases |
|---|---|---|
| CKB tx pool's size limit (`TRANSACTION_SIZE_LIMIT`) | 512,000 bytes | PR #34's final transaction is 81,889 bytes (16%). The Sigsheet file itself never goes on chain |
| The lock's witness buffer | 32 KB ([background §1](../../background.md#1-the-multisig-lock)) | The largest possible multisig lock (N = M = 255) is 21,679 bytes |
| Relay message limits seen in NIP-11 examples | 16,384 / 65,535 / 524,288 bytes ([background §15](../../background.md#15-ckb-limits-the-indexer-and-the-nervos-dao)) | PR #34 as a whole file (733,078 bytes as C, 367,378 as A) exceeds all three; one posted signature (367 bytes) fits all |
| Ledger Nervos app 0.6.3 (XQ14) | five non-change outputs; genesis multisig only; no size limit up to a 2 MB stream on the emulator | PR #34 is refused for its lock and shape, not its size |

## Answer

The real cases are 2.4 KB (the genesis 2-of-3 payment) to 733 KB (PR #34) as C; A halves the uncompressed size and B's per-input layout nearly doubles PR #34. Every operation takes well under a second in the patched ckb-cli and under 2 s in CCC including start-up, for the largest real case. No limit stops the format: the final transactions are far below CKB's limits; a whole PR #34 file is too big for any of the relay message limits seen, but one signer's signature, with the ids that place it, is 367 bytes.
