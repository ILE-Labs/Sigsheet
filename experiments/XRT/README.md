# XRT: attacks and objections considered, first round

**Question:** attacks and objections raised against the design say it mishandles some transactions or can be attacked. Which of them hold, measured on the local devnet or with the prototypes, and does each candidate rule fix it? How the design answers each: [design record §5](../../design-record.md#5-security-analysis).

| Part | What it measures | Where it runs |
|---|---|---|
| XRT-1 `scripts/genesis_sweep.py` | Which valid signature sets each deployed multisig binary accepts (a member at position ≥ M; a key listed twice) | devnet: `test_tx_pool_accept` (the node's full verification; nothing committed) |
| XRT-2 `scripts/prototype_checks.py` | Merge hygiene (entries no input uses), junk signatures, the canonical check before dropping, non-canonical templates, one out point twice | the prototypes, offline |
| XRT-3 `scripts/unknown_groups.py` | A lock the reader doesn't sign; carrying another group's signature; since flags under the genesis lock | devnet: two transactions committed, one dry run |
| XRT-4 `scripts/creation_flows.py`, `ccc-create/`, `ckb-cli-creation.diff` | Creating the file inside the wallets | devnet: two transactions committed |

**Method.** Fresh test keys only, made at run time into `keys/xrt/` at the repository root (a link to a folder outside the checkout; the scripts refuse to write keys inside it), plus X1's miner key k0 to fund. The prototypes ([`../prototypes/`](../prototypes/README.md)) are used unchanged; candidate rules are written in the scripts.

For XRT-4, ckb-cli is X6's patched ckb-cli plus a `tx sigsheet-new` subcommand: [`ckb-cli-creation.diff`](ckb-cli-creation.diff) applies on top of [`../X6/ckb-cli/patch.diff`](../X6/ckb-cli/patch.diff) (license: [`NOTICE.md`](NOTICE.md)). CCC is X6's patched core and harness, unchanged, plus `ccc-create/create.ts`. ckb-cli's own `tx init`, `add-multisig-config`, `add-input` and `add-output` run from the released ckb-cli 2.0.0 binary (the same commit, `80efc21`): in a debug build, ckb-cli's `tx add-output` panics on clap's debug-only argument check ("Argument or group 'multisig-code-hash' specified in 'requires*' for 'to-long-multisig-address' does not exist"), which is upstream code, not the patch.

## Exact commands

From `experiments/XRT/`, with X1's devnet running (`ckb run -C devnet/node` and `ckb miner -C devnet/node` from the repository root):

```sh
mkdir -p results
python3 -I -X utf8 scripts/genesis_sweep.py > results/genesis-sweep.json 2> results/genesis-sweep-run2.log
python3 -I -X utf8 scripts/genesis_sweep.py --positions > results/genesis-positions.json 2> results/genesis-positions.log
python3 -I -X utf8 scripts/prototype_checks.py > results/prototype-checks.json 2> results/prototype-checks.log
python3 -I -X utf8 scripts/unknown_groups.py > results/unknown-groups.json 2> results/unknown-groups.log
# XRT-4: a ckb-cli copy with X6's patch and the creation diff, built; then the flows
mkdir -p ckb-cli-src && git -C ../../refs/ckb-cli archive 80efc21c30e9fc7847407a217034681b6e46c763 | tar -x -C ckb-cli-src
(cd ckb-cli-src && patch -p1 < ../../X6/ckb-cli/patch.diff && patch -p1 < ../ckb-cli-creation.diff)
(cd ckb-cli-src && CARGO_HOME=$PWD/../../../refs/_cargo-home RUSTUP_TOOLCHAIN=stable cargo build --locked)
python3 -I -X utf8 scripts/creation_flows.py > results/creation.json 2> results/creation.log
(cd ckb-cli-src && CARGO_HOME=$PWD/../../../refs/_cargo-home RUSTUP_TOOLCHAIN=stable cargo test --locked > ../results/ckb-cli-test-with-creation.log 2>&1)
```

`results/genesis-sweep-run1.log` is the first run's progress log: that run crashed at its last step (the repeated-key case, which the prototype's reader refuses by design), so its per-set detail wasn't written; run 2 repeated it on fresh cells with the message computed by X1's implementation directly.

`./bench/run.sh` (benchmark `xrt2`) re-runs XRT-2 offline and compares its outcomes with `results/prototype-checks.json`; its two times are shown for reference only.

## Environment

2026-11-19 (UTC); local devnet (ckb 0.210.0; the genesis multisig binary byte-identical to mainnet's, the 2024 and v2 binaries copied from mainnet, as in X1); Python 3.14.4; rustc 1.100.0 (stable); Node v22.22.1 with X6's harness's tsx (`TMPDIR` set to a temporary folder). Nothing was sent anywhere but the local devnet.

## Files

`scripts/`, `ccc-create/`, `ckb-cli-creation.diff` and `NOTICE.md`, `results/`, `results.md`. The ckb-cli copy (`ckb-cli-src/`) and its `target/` are working folders, git-ignored and not in this branch. XRT-2's raw output omits one check of the recorded run, which read third-party test data that this branch doesn't carry; the Nervos DAO fee is measured on the devnet in [XRTb-3](../XRTb/results.md#xrtb-3-a-nervos-dao-withdrawal-of-two-deposits).
