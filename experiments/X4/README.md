# X4: is each attack caught, and by which check, in each format?

**Questions:**
1. Does each deployed multisig lock accept a malleated (high-s) signature? X3a found it by reading the code; the case against BIP-174's and PCZT's merge rules leans on it.
2. For each attack (falsified input cells, a swapped transaction, altered outputs or fees, signatures from non-members, junk that blocks finalizing, replay; plus a swapped config, a changed covered witness, display fields, and path A's `resolved_inputs`), build the malicious file in each candidate format (C, B+w, A) and record which check catches it.

## Method and exact commands

From `experiments/X4/` (steps 1 and 3 need the devnet, the cells funded by `../X5/scripts/fund_s4.py` and the test keys in `keys/s4/` at the repository root; step 2 runs offline):

```sh
python3 -I -X utf8 scripts/high_s_devnet.py > results/high-s-devnet.json   # 1. on all three deployments
python3 -I -X utf8 scripts/x4.py > results/x4.json                        # 2. malicious files, every format
python3 -I -X utf8 scripts/replay_devnet.py > results/replay-devnet.json  # 3. replay on the devnet (after X5 F1)
```

1. `high_s_devnet.py`: for each deployment, a fresh 2-of-3 cell [s1, s2, s3]; both members sign (low-s, as wallets do); `test_tx_pool_accept` on that transaction (control); then s1's signature is replaced by its twin (s → N − s, recovery bit flipped, which recovers to the same key over the same message); dry run, `send_transaction`, wait until committed; also a dry run with both signatures replaced.
2. `x4.py`: base case the real genesis 2-of-3 payment (R2: two real signatures, from X2). Each attack writes a malicious file in C, B+w and A; the "reader" is what an honest Sigsheet tool does with a received file: strict decoding (schema, canonical form, every profile rule), `core.validate`, the signer's view (which signatures verify), and a finalize attempt. Then a merge of the honest file with the malicious one.
3. `replay_devnet.py`: send again a transaction X5 committed; and put its witness (two valid signatures) on a new transaction spending a fresh cell of the same multisig.

## Environment

2026-11-18 (UTC); the prototypes (`../prototypes/`); the local devnet (ckb 0.210.0; genesis holds the three deployments' binaries copied from mainnet, X1's Devnet row); fresh test keys s1-s6 (`keys/s4/` at the repository root, not in this branch); cells from `../X5/data/funding.json`.

## Files

`scripts/`, `results/` (`high-s-devnet.json`, `x4.json`, `replay-devnet.json`), `results.md`.
