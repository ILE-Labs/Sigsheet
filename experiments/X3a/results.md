# X3a results: merging partial signatures in any order

Conditions (design-stage): 2026-11-18 (UTC). fiber-scripts PR #34's transaction `0x4396de69…92ee` (3-of-5 v2 multisig, R = 0, plus one single-key input) and its five real member signatures, from X1's mainnet data; message `0xba2c497a…0348`, the same as in X1's table. CCC `@ckb-ccc/core` 1.23.1, offline. Python checks with X1's independent implementation. Nothing sent to any chain. Commands in `README.md`; raw output in `results/`.

## 1. CCC's `aggregateTransactions` depends on the order of the files

Five partial files, one signature each; all 120 orders (`results/ccc-analysis.json`):

| Measure | Result |
|---|---|
| Results valid under the lock's rules (length, M distinct members) | **120 of 120** |
| Distinct multisig witnesses produced | **60** (10 member sets × 6 orders of the three signatures) |
| Members kept | always the first three in input order (120 of 120); the other two signatures are dropped |
| Single-key input's signature kept | **24 of 120** orders, exactly those where the file carrying it came first |
| Transaction hash | unchanged in all 120 |

The code shows why (`packages/core/src/signer/ckb/signerMultisigCkbReadonly.ts` at `7095cca`): the result starts from `Transaction.from(txs[0])` (L688), so every witness outside the multisig group comes from the first file; the loop stops once it holds M signatures (L729, L734); and a lock of exactly M slots has no room for more.

So "merge with CCC's `aggregateTransactions`" is valid in any order, but **not order-independent**: the same five files give 60 different witnesses, and in 96 of 120 orders the merge silently loses another signer's single-key signature.

## 2. Only the candidate rule gives one result in any order, with junk

2,000 trials; each merges the same files in two random orders (`results/merge-rules.json`):

| Rule | Same result both ways | Merge failed | Invalid final lock |
|---|---:|---:|---:|
| **Candidate:** verify; members only; normalize to low-s; key by signer; finalize with the first R, then the lowest member indices, in member order | **2,000** | 0 | 0 |
| First-seen (BIP-174's Combiner "can pick arbitrarily when conflicts occur") | 1,285 | 0 | 0 |
| Strict (PCZT: fail when one key has two values) | 2,000 | **1,531** | 0 |
| CCC-like (keep the first M verified, in order) | 456 | 0 | 0 |

- With only the five real signatures (no twins, no junk), the candidate, first-seen and strict rules all agree in 2,000 of 2,000; CCC-like still differs in 1,636.
- The candidate rule is idempotent (merging the same files twice changes nothing) in 2,000 of 2,000.
- **First R:** with R = 2, M = 3, N = 5 (fresh test keys), the candidate finalizes with members 0, 1 and 2 when all five signed, and the lock passes the lock's rules; with member 0 missing it refuses to finalize, though four members signed.
- Junk (random bytes, a non-member's valid signature, a signature over another message) never reached a final lock under any rule; every rule verifies first.

## 3. A member can have two valid signatures with different bytes

- **The malleated twin** (s replaced by N − s, recovery bit flipped) of each of the five real signatures recovers to the same member: in X1's Python implementation, and in CCC's `recoverMessageSecp256k1` (5 of 5, `results/high-s.json`).
- **The lock accepts it, by code reading (not run on chain).** The multisig lock calls `secp256k1_ecdsa_recoverable_signature_parse_compact` and `secp256k1_ecdsa_recover` (`c/secp256k1_blake160_multisig_all.c` L306, L314 at `72eb92f`). In the secp256k1 it is built with (nervosnetwork/secp256k1 `3ffde18`), parsing rejects only r or s at or above the group order ([`src/modules/recovery/main_impl.h` L38-L58](https://github.com/nervosnetwork/secp256k1/blob/3ffde18a060aaf4df5b81e7d88355f1e99874650/src/modules/recovery/main_impl.h#L38-L58)), and recovery rejects only zero values and invalid points ([L87-L119](https://github.com/nervosnetwork/secp256k1/blob/3ffde18a060aaf4df5b81e7d88355f1e99874650/src/modules/recovery/main_impl.h#L87-L119)). Neither checks for low-s. A devnet run confirmed it ([X4](../X4/results.md#1-the-lock-accepts-a-malleated-signature-on-all-three-deployments-run-on-chain)).
- **Consequence:** anyone who sees a member's signature can post a second valid one. Under PCZT's rule that makes combining fail (1,531 of 2,000 trials); under first-seen the result depends on order (715 of 2,000). The fix is a rule that chooses deterministically, such as normalizing to low-s.

## Answer

1. CCC's `aggregateTransactions` isn't an order-independent merge: same files, 60 different results, the first M kept, and other inputs' signatures lost unless their file comes first. Path D's "fully associative, commutative, and idempotent" merge (path D section 4) doesn't hold for the code it cites.
2. A merge that keeps every verified member signature keyed by signer, normalized to low-s, and finalizes deterministically (first R, then the lowest member indices, in member order) gives one result in any order and any number of merges, with junk and twins: 2,000 of 2,000.
3. BIP-174's arbitrary choice and PCZT's strict failure both break on malleated twins, which the lock appears to accept. Path B's rule must change.
4. An in-witness layout with exactly M slots can't keep signatures beyond M before finalizing; a map keyed by signer can (PR #34 gathered 5 for 3, [background §12](../../background.md#12-the-real-cases)).
