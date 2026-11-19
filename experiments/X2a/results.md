# X2a results: the bytes each format must carry

Conditions (design-stage): 2026-11-18 (UTC); X1's mainnet data; every transaction hash recomputed and matched (`results/sizes.json`).

| | PR #34 (3-of-5 v2 deploy) | The genesis 2-of-3 payment |
|---|---:|---:|
| Transaction, Molecule (raw + witnesses) | 81,889 | 589 |
| Transaction, compact hex JSON | 163,901 | 1,214 |
| Previous transaction(s) proving the inputs, Molecule, with witnesses | 284,468 (1 transaction; both inputs come from it) | 589 |
| The same, compact hex JSON, with witnesses | 569,132 | 1,213 |
| The same, Molecule raw transaction only (no witnesses) | 284,008 | 351 |
| The same, compact hex JSON without the `witnesses` field | 568,285 | 766 |
| **Transaction + proof with its witnesses: binary / hex JSON** | **366,357 / 733,033** | **1,178 / 2,427** |
| Hex JSON over binary, proof with witnesses | +366,676 bytes (×2.001) | +1,249 bytes (×2.060) |
| **Transaction + proof without its witnesses: binary / hex JSON** | **365,897 / 732,186** | **940 / 1,980** |
| Hex JSON over binary, proof without witnesses | +366,289 bytes (×2.001) | +1,040 bytes (×2.106) |
| Data of the cells the transaction spends (what path A's `resolved_inputs.outputs_data` repeats) | 79,880 | 0 |
| Saved by carrying the previous transactions' raw part only (no witnesses), in binary | 460 | 238 |

Each comparison is like for like: the transaction is whole on both sides (its witnesses hold the signatures), and the proof is either whole on both sides or without its witnesses on both sides. (The first version of this table, run earlier on 2026-11-18, set the binary proof without witnesses against the JSON proof with witnesses; a review caught it, and `sizes.py` now reports both pairs.)

- **Hex JSON doubles the bytes,** like for like: ×2.001 for PR #34 (about 367 KB more) and ×2.06-×2.11 for the genesis 2-of-3 payment (about 1.0-1.2 KB more). The proving transaction is the bulk in a deployment: one 284,008-byte raw transaction proves both of PR #34's input cells.
- **Path A's duplication** of the spent cells' data is 79,880 bytes for PR #34, not the 363,992 an earlier estimate counted.
- **A raw-only proof** (without the previous transaction's witnesses) is enough to check an out point, since the hash covers the raw transaction only ([background §2](../../background.md#2-transaction-structure-and-hash)); it saves a few hundred bytes here.
- **A proof can't be trimmed further.** The hash covers the whole raw transaction, outputs data included, so a signer who checks an input cell offline must hash all 284,008 bytes. A "trimmed previous transaction" wouldn't hash to the out point.
