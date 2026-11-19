# X1: does every tool compute the same signing message?

**Question:** do ckb-cli, Neuron and CCC compute the same signing message, byte for byte, for every real and synthetic case? Where does each one compute it?

**Answer** (design-stage; [results.md](results.md)): yes on all 15 lock groups for CCC, ckb-cli and ckb-sdk; yes on 12 of 13 multisig groups for Neuron, which differs only when the transaction has a witness beyond its inputs.

Run on 2026-11-18 (UTC) on a Linux machine with 2 CPUs and 7.6 GB RAM.

## Method

Four implementations compute the message of every lock group in every case:

| Tag | Implementation | How it runs | Where the message is computed (pinned) |
|---|---|---|---|
| M | An independent implementation, written from the specs and the lock's C source ([`scripts/ckbcore.py`](scripts/ckbcore.py), standard library only) | `scripts/messages_python.py` | `multisig_message` and `sighash_all_message` in `scripts/ckbcore.py` |
| C | CCC, `@ckb-ccc/core` 1.23.1 from npm (`ccc/package-lock.json`) | `ccc/x1-ccc.mjs`, offline: input cells come from the case file into CCC's cache; the RPC URL points at a closed port | [`Transaction.getSignHashInfo`, transaction.ts L1480-L1516](https://github.com/ckb-devrel/ccc/blob/7095ccad564b94ea2e59284cb4a364aa3499252e/packages/core/src/ckb/transaction.ts#L1480-L1516); multisig through [`SignerMultisigCkbReadonly.getSignInfo`, L649-L675](https://github.com/ckb-devrel/ccc/blob/7095ccad564b94ea2e59284cb4a364aa3499252e/packages/core/src/signer/ckb/signerMultisigCkbReadonly.ts#L649-L675) |
| R | ckb-cli 2.0.0, two ways: (a) the released binary signs through its own `tx` files; (b) `rust/`, a harness that compiles ckb-cli's own `build_signature` plus ckb-sdk 5.0.0's script signers, with ckb-cli v2.0.0's `Cargo.lock` | (a) `scripts/ckbcli_sign.py`; (b) `rust/target/release/x1-rust-paths <case>` | ckb-cli: [`build_signature`, tx_helper.rs L507-L566](https://github.com/nervosnetwork/ckb-cli/blob/80efc21c30e9fc7847407a217034681b6e46c763/src/utils/tx_helper.rs#L507-L566), called from `sign_inputs` (L226-L294). ckb-sdk: [`generate_message`, signer.rs L475-L538](https://github.com/nervosnetwork/ckb-sdk-rust/blob/3a418e7048c8864c15548e838072495edefbc24f/src/unlock/signer.rs#L475-L538) |
| N | Neuron v0.204.1 (`d3a7467`), its own TypeScript run in Node under its own jest setup | A jest harness built from Neuron's own test file (`neuron/make_harness.sh`) | [`signSingleMultiSignScript`, transaction-sender.ts L449-L490](https://github.com/nervosnetwork/neuron/blob/d3a7467d218e4b6f777326682a83fec802669c00/packages/neuron-wallet/src/services/transaction-sender.ts#L449-L490), called by `signMultisig` (L290-L447) |

The lock script's own rule, which all of them must match: [secp256k1_blake160_multisig_all.c L205-L281](https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c#L205-L281).

Then:
1. Each tool signs with the designated test keys. Every signature from every tool is checked against message M by public-key recovery (`scripts/assemble.py`).
2. On a local devnet, each synthetic case is finalized with signatures taken from different tools and sent; `test_tx_pool_accept` runs first. Two negative controls must be rejected.
3. Case S1 is finalized by ckb-cli itself: Neuron's and CCC's signatures are added to ckb-cli's `tx` file with `tx add-signature`, and `ckb-cli tx send` builds the witness and submits it.
4. Case S8 is a real Neuron export: Neuron's own `OfflineSignController.exportTransactionAsJSON` writes it after the first signature; then `scripts/s8_neuron_export.py` checks it with no node, and `ccc/s8-read-neuron.mjs` tests whether CCC reads it.

## Cases (`cases/*.json`)

| ID | What it covers |
|---|---|
| R1-fiber-scripts-pr34 | fiber-scripts PR #34: the `cell_tx` of `deployment/mainnet/mainnet.json` at `026027f` (SHA-256 `8563ba8d…b51e`): a 3-of-5 v2 multisig input next to a single-key input. All six real signatures (one in the file per lock, four pasted in PR comments) are checked. Committed on mainnet in block 20,965,430. A mainnet input ([mainnet-inputs.md](../mainnet-inputs.md)) |
| R2-dao-payout | A 2-of-3 genesis multisig payment on mainnet, tx `0x63a7f3a5…baa4`, block 20,354,743. A mainnet input |
| S1-genesis-2of3 | Genesis deployment (type `0x5c5069eb…`), 2-of-3 |
| S2-2024-2of3 | 2024 deployment (binary from mainnet; devnet type id `0x6283a479…`), 2-of-3 |
| S3-v2-2of3-two-inputs | v2 (`data1` `0x36c971b8…`), two inputs in one lock group |
| S4-v2-first-R | v2, R = 1: the first key must sign |
| S4N-v2-first-R-missing-required | Negative control for S4: two members sign, but not the required one |
| S5-v2-since-in-args | v2, lock args with a since (absolute block 20); the input's since is 20 |
| S6-two-multisig-groups | Two multisig lock groups: genesis 2-of-3 and v2 3-of-5 |
| S7-multisig-plus-single-key | A v2 multisig input next to a single-key input |
| S8-neuron-export | A Neuron-style export: signed first in Neuron and exported by Neuron's own code, then completed |
| S9-extra-witness | A witness beyond the inputs (4 bytes at index 1), which the lock hashes |

## Environment and versions

| Item | Version |
|---|---|
| ckb (devnet node and miner) | `ckb 0.210.0 (2592ddf 2026-09-17)` |
| ckb-cli | `ckb-cli 2.0.0 (80efc21 2025-12-03)`; source at tag v2.0.0 = `80efc21c30e9fc7847407a217034681b6e46c763` |
| ckb-sdk (Rust) | 5.0.0 from crates.io (checksum in `rust/Cargo.lock`, copied from ckb-cli v2.0.0's lockfile); source tag v5.0.0 = `3a418e7048c8864c15548e838072495edefbc24f` |
| CCC | `@ckb-ccc/core` 1.23.1 from npm (`ccc/package-lock.json`); source tag `@ckb-ccc/core@1.23.1` = `7095ccad564b94ea2e59284cb4a364aa3499252e` |
| Neuron | tag v0.204.1 = `d3a7467d218e4b6f777326682a83fec802669c00`, dependencies from its `yarn.lock` (`yarn install --frozen-lockfile --ignore-scripts`) |
| Node, Python, Rust | Node v22.22.1, Python 3.14.4, rustc 1.100.0 |
| Devnet | `devnet/node` at the repository root (git-ignored). Chain spec = `ckb init --chain dev`, plus: the 2024 and v2 multisig binaries copied from mainnet cells `0x0a13d8d9…55d8:0` and `0x3e27a1a2…a282:0` as genesis system cells with two more dep groups; the issued cells go to fresh test keys only; P2P bound to 127.0.0.1; Indexer RPC on; 1-second blocks (`scripts/devnet_setup.py`). `data/devnet/genesis-info.json` records the hashes: the bundled genesis multisig binary is byte-identical to mainnet's (data hash `0x43400de1…3bfb`, type hash `0x5c5069eb…e2a8`) |
| Keys | 8 fresh keys from `os.urandom`, made by `scripts/keygen.py` into `keys/x1/` at the repository root (see [the experiments' README](../README.md#what-isnt-in-this-branch-and-the-local-folders-that-replace-it)); not in this branch |

## Exact commands

From `experiments/X1/` unless noted. `keys/`, `refs/` and `devnet/` are at the repository root and git-ignored.

```sh
# 0. The mainnet inputs (read-only JSON-RPC and GitHub; see ../mainnet-inputs.md)
python3 -I -X utf8 scripts/fetch_mainnet.py                      # data/mainnet/*; checks every transaction hash
curl -sfA 'research-script/1.0' -o data/fiber-scripts-34/mainnet.json \
  https://raw.githubusercontent.com/nervosnetwork/fiber-scripts/026027f54f6a90cb48d8cc184b230e2018bb8611/deployment/mainnet/mainnet.json
sha256sum data/fiber-scripts-34/mainnet.json                     # 8563ba8dcd0d0518...b51e
python3 -I -X utf8 ../../bench/fetch_mainnet.py --comments-only  # data/fiber-scripts-34/comment-1..4.txt from PR #34

# 1. Keys (outside the checkout) and the devnet
ln -s "$(mktemp -d)" ../../keys && mkdir -p ../../keys/x1 && python3 -I scripts/keygen.py 8 ../../keys/x1/keys.json
mkdir -p ../../devnet && cd ../../devnet && ckb init --chain dev -C node --ba-arg <k0 blake160> \
  --ba-code-hash 0x9bd7e06f3ecf4be0f2fcd2188b23f1b9fcc88e5d4b65a8637b17723bbda3cce8 --ba-hash-type type --ba-message 0x
cd ../experiments/X1 && python3 -I -X utf8 scripts/devnet_setup.py ../../devnet/node
#    data/devnet/dev.toml is the exact spec this run used. `ckb init` sets [genesis.genesis_cell] message from the
#    clock; this run's was "1794962377977". Use that value to get the same genesis hash (0x6d63ea15...cde2).
#    Then, in two terminals:  ckb run -C devnet/node   and   ckb miner -C devnet/node   (from the repository root)
python3 -I -X utf8 scripts/devnet_info.py                        # data/devnet/genesis-info.json

# 2. Cases (funds the multisig cells on the devnet)
python3 -I -X utf8 scripts/build_cases.py
python3 -I -X utf8 scripts/build_cases.py --extra                # S4N

# 3. The four implementations
python3 -I -X utf8 scripts/messages_python.py                    # M -> results/python.json
(cd ccc && npm_config_cache=$PWD/../../../refs/_npm-cache npm ci && node x1-ccc.mjs ../cases ../../../keys/x1/keys.json ../results/ccc.json)
sh rust/make_tx_helper.sh ../../refs/ckb-cli                     # rust/src/ckb_cli_tx_helper.rs, from ckb-cli at 80efc21
(cd rust && CARGO_HOME=$PWD/../../../refs/_cargo-home cargo build --release)   # rust/Cargo.lock is ckb-cli v2.0.0's lockfile
for f in cases/*.json; do rust/target/release/x1-rust-paths $f > results/rust/$(basename $f .json).jsonl; done
python3 -I -X utf8 scripts/ckbcli_sign.py                        # ckb-cli binary -> results/ckb-cli.json
python3 -I -X utf8 scripts/ckbcli_sign.py S4N-v2-first-R-missing-required
#    Neuron: a checkout at d3a7467 in refs/neuron-x1, its dependencies, the harness, then the test
(cd ../../refs/neuron-x1 && npm_config_cache=$PWD/../_npm-cache YARN_CACHE_FOLDER=$PWD/../_yarn-cache ELECTRON_SKIP_BINARY_DOWNLOAD=1 \
  npx yarn@1.22.22 install --frozen-lockfile --ignore-scripts)
(cd neuron && sh make_harness.sh ../../../refs/neuron-x1)       # tests/x1/x1-neuron.test.ts
(cd ../../refs/neuron-x1/packages/neuron-wallet && X1_CASES=$OLDPWD/cases X1_KEYS=$OLDPWD/../../keys/x1/keys.json \
  X1_OUT=$OLDPWD/results/neuron.json X1_EXPORT_DIR=$OLDPWD/results/neuron-export X1_CONTEXT_DIR=$OLDPWD/data/devnet \
  ../../node_modules/.bin/jest tests/x1/x1-neuron.test.ts)

# 4. Verify every signature; finalize mixed-tool transactions on the devnet; negative controls
python3 -I -X utf8 scripts/assemble.py                           # results/verify.json, results/assembly.json
python3 -I -X utf8 scripts/s8_neuron_export.py                   # results/s8-neuron-export.json
(cd ccc && node s8-read-neuron.mjs ../results/neuron-export/S8-neuron-export-after-first-signature.json)
(cd ccc && node ckbcli-json-from.mjs ../results/ckb-cli/S3-v2-2of3-two-inputs.json ../cases/S3-v2-2of3-two-inputs.json)
python3 -I -X utf8 scripts/summarize.py                          # results/message-table.md
python3 -I -X utf8 scripts/ckbcli_threshold_check.py             # side check: ckb-cli with M+1 signatures, then M
python3 -I -X utf8 scripts/measure_pr34.py                       # bytes of each field in the PR #34 deploy file -> results/pr34-size.json
```

`scripts/assemble.py` can be run again: it skips cases already committed and keeps earlier results. The independent implementation's messages are re-checked offline by `./bench/run.sh` (benchmark `x1`).

## Files

- `scripts/`: the experiment's code (Python, standard library only).
- `ccc/`, `rust/`, `neuron/`: the harnesses for C, R and N. `rust/ckb_cli_tx_helper.diff` and `neuron/x1-neuron.test.diff` are this experiment's changes to excerpts of ckb-cli's and Neuron's own files; `make_tx_helper.sh` and `make_harness.sh` rebuild the harness files from a checkout at the pinned commit (licenses: `NOTICE.md` in each folder).
- `cases/`: the case files (unsigned transaction, resolved input cells, lock groups, signers). R1 and R2 are mainnet inputs, not in this branch.
- `data/devnet/`: the devnet's genesis record and chain spec, the funding transactions, and the committed transactions (`committed/`). `data/mainnet/` and `data/fiber-scripts-34/` are mainnet inputs, not in this branch.
- `results/`: raw output of every tool, `verify.json`, `assembly.json`, `message-table.md`, Neuron's export.

## Notes on the run

- The first run of `assemble.py` crashed after S1-S5 were committed (a harness bug: two signatures were missing from its table). Its screen output, including ckb-cli's `tx send` log for S1 and the first negative results, was lost. What remains for S1: ckb-cli's `tx` file `results/ckb-cli/S1-genesis-2of3.json` holds the two signatures that `tx add-signature` wrote, and the committed witness is in `data/devnet/committed/S1-genesis-2of3.json`. The S4 negative control was redone on a fresh cell as S4N, because S4's input was spent.
- A first CCC harness run read the wrong signature slot for second signers (CCC's `signOnlyTransaction` filled the shared transaction object in place, since `Transaction.from` returns an existing instance unchanged). Fixed by giving each signer `tx.clone()`. CCC's messages weren't affected.
