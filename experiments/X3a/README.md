# X3a: merging partial signatures in any order

A first test of the merge rules, on PR #34's real signatures, made to settle the objections raised against the candidate merge rules: whether CCC's in-witness merge is order-independent, and whether BIP-174's and PCZT's conflict rules survive a member's second valid signature. [X3](../X3/README.md) runs every format's merge in full on the prototypes.

## Questions

1. Does CCC's `aggregateTransactions`, which path D (and others) cite as their merge, give the same result whatever order the partial files come in? What does it keep when more than M signatures exist, and what happens to other inputs' signatures?
2. Which merge rule gives the same final witness in any order, any number of times, with junk in the files: BIP-174's (a Combiner "can pick arbitrarily when conflicts occur"), PCZT's (fail when one key has two values), CCC's, or the candidate rule (verify, keep members, normalize to low-s, key by signer, finalize deterministically)?
3. Does the existing multisig lock accept a signature's malleated twin (high-s)? If it does, one member can have two valid signatures with different bytes, and a merge rule must choose between them.

## Method

1. `scripts/build_partials.py`: from X1's PR #34 case (`experiments/X1/cases/R1-fiber-scripts-pr34.json`, the transaction committed on mainnet) and X1's copies of the PR's five real member signatures (the deploy file's `cell_tx_signatures` and the four PR comments), recompute the 3-of-5 group's message with X1's independent implementation, recover each signature to its member, and write five one-signature partial transactions in CCC's layout (final-length lock, zero-filled slots). The single-key input's real signature goes only into the partial of member 1, who owns that input.
2. `ccc/aggregate_orders.mjs`: CCC 1.23.1's `SignerMultisigCkbReadonly.aggregateTransactions` on the five partials in all 120 orders, offline (input cells in CCC's cache, RPC URL at a closed port, as in X1).
3. `scripts/analyze_ccc.py`: check every result against the lock's rules (exact length; M signatures recovering to M distinct members; the first R) with X1's implementation; count distinct witnesses, kept member sets, and orders where the single-key signature survived.
4. `scripts/merge_rules.py`: property tests of four merge rules on a pool of the five real signatures, their five malleated twins and three junk entries (65 random bytes; a valid signature by a fresh non-member key; the PR's single-key signature, which is over a different message). 2,000 trials, each drawing 2-6 files of 1-4 entries and merging them in two random orders and fold directions; plus the same with only the real signatures; idempotence; and a first-R test (R = 2, M = 3, N = 5, fresh test keys).
5. `ccc/high_s.mjs`: does CCC's `recoverMessageSecp256k1` accept the malleated twins?
6. For question 3, the secp256k1 code the lock is built with was read: ckb-system-scripts `72eb92f` pins the submodule `deps/secp256k1` at nervosnetwork/secp256k1 `3ffde18a060aaf4df5b81e7d88355f1e99874650` (2019-07-30), cloned into `refs/nervos-secp256k1`.

## Exact commands

From `experiments/X3a/` (the `ccc/node_modules` link points at X1's install of `@ckb-ccc/core` 1.23.1):

```sh
python3 -I -X utf8 scripts/build_partials.py > results/partials.json
node ccc/aggregate_orders.mjs results/partials.json results/ccc-orders.json
python3 -I -X utf8 scripts/analyze_ccc.py > results/ccc-analysis.json
python3 -I -X utf8 scripts/merge_rules.py 2000 > results/merge-rules.json
node ccc/high_s.mjs results/partials.json results/high-s.json
```

## Environment and versions

2026-11-18 (UTC), on a Linux machine with 2 CPUs. Python 3.14; Node v22.22.1; `@ckb-ccc/core` 1.23.1 (X1's install). Mainnet data from X1 (fetched from `https://mainnet.ckb.dev/` on 2026-11-18). ckb-system-scripts `72eb92fca090700dcb398cd8cad8fbd8bad40355`; its secp256k1 at `3ffde18a060aaf4df5b81e7d88355f1e99874650`. Nothing was sent to any chain. The test keys of the first-R test and the non-member key are made by `merge_rules.py` at run time and never stored (the recorded run derived them from fixed strings; the counts don't depend on the key bytes, and `./bench/run.sh` reproduces them).

## Files

- `scripts/`: the Python steps; `ccc/`: the two Node scripts and `package.json`.
- `results/`: `partials.json`, `ccc-orders.json`, `ccc-analysis.json`, `merge-rules.json`, `high-s.json`.
- `results.md`: the answers and numbers.
