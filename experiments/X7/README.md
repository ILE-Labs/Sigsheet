# X7: the numbers (sizes, times, limits)

**Question:** file sizes for the real and synthetic cases in each candidate format; how long reading, verifying, merging and finalizing take; and the limits that matter.

## Method and exact command

`scripts/x7.py`, from `experiments/X7/` (the patched ckb-cli and CCC from X6 must be built; point `TMPDIR` at a folder you can delete afterwards):

```sh
TMPDIR=<a temporary folder> npm_config_cache=$PWD/../../refs/_npm-cache python3 -I -X utf8 scripts/x7.py > results/x7.json
```

1. **Sizes:** every case and format, from X2's results (`../X2/results/x2.json`); and the smallest thing a signer can post on its own: one signature with the ids that place it (`unsigned_id`, the lock group, the signer), as canonical JSON.
2. **Times in the Python prototypes,** median of 5 runs (3 for the many-file merge): decode and validate; the messages; a merge of two partial files; a merge of one file per signature; finalize. Pure Python, including a pure-Python secp256k1 (X1's), so these are upper bounds; recovering one public key takes about 20 ms of it.
3. **Times in the patched wallets** on the largest real case, PR #34 (733,078 bytes as C), offline: ckb-cli and CCC each merge two partial files (three and three signatures) and finalize; median of 3 runs of the whole process (start-up included; CCC also reports its in-module time).
4. **Limits:** CKB's tx-pool size limit (`TRANSACTION_SIZE_LIMIT`, ckb [`util/types/src/core/tx_pool.rs` L309](https://github.com/nervosnetwork/ckb/blob/2592ddf0502cd4adfe886db893cccc866db3c60f/util/types/src/core/tx_pool.rs#L309) at `2592ddf`), the lock's witness bound ([background §1](../../background.md#1-the-multisig-lock)), the largest possible multisig lock, and the relay message limits in NIP-11's examples ([background §15](../../background.md#15-ckb-limits-the-indexer-and-the-nervos-dao)).

`./bench/run.sh` (benchmark `x7`) re-runs parts 1 and 2 offline: the posted signature's size is compared with this run's, and the prototype times are shown next to this run's, for reference only.

## Environment

2026-11-19 06:52 UTC; Python 3.14.4; the X6 debug build of ckb-cli; CCC's patched core under tsx 4.20.6 on Node v22.22.1; offline (no node needed); a Linux machine with 2 CPUs.
