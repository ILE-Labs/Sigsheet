# The benchmark runner

```sh
./bench/run.sh
```

One command, from the repository root. It re-runs every design-stage benchmark that works offline on a plain machine and prints each measured value next to the recorded one. The recorded values are the experiments' own result files (`experiments/*/results/`), measured on throwaway prototypes and patched copies of the wallets; the runner only reads them.

## Prerequisites

- **Python 3**, standard library only. Tested with Python 3.14.4 on Linux.
- **A POSIX shell.** Nothing else: no network, no Node, no Rust, no devnet, no sudo.
- **The optional steps need more:** `fetch-mainnet.sh` needs network access; `wallets.sh` needs git and GNU patch (tested with patch 2.8); the devnet and wallet steps need ckb 0.210.0, ckb-cli 2.0.0, Node v22.22.1 and rustc 1.100.0 ([experiments/README.md](../experiments/README.md#tools-and-versions)).
- **Time:** on a 2-CPU machine, about 4 minutes, or about 7 with the mainnet inputs present. `./bench/run.sh --full` runs X3 with its recorded trial count (200 per case and format), which takes about an hour.

## What it runs

| Benchmark | What it re-runs | Compared with |
|---|---|---|
| `x1` | The signing message of every lock group, from X1's independent implementation | `experiments/X1/results/python.json` |
| `x2` | Every format's round trip, size (and zlib size), the CoBuild mapping both ways, and the fields a signer's message reads | `experiments/X2/results/x2.json` |
| `x3` | Merging in any order, with junk, twins and repeats, in C, B+w and A; keys by lock group; first R. On offline copies of X3's devnet cases, with keys made at run time and never written; a fixed seed for the trials | `experiments/X3/results/x3.json` |
| `x3a` | The four merge rules on PR #34's five real signatures, 2,000 trials, fixed seed | `experiments/X3a/results/merge-rules.json` |
| `x4` | Every offline attack in every format | `experiments/X4/results/x4.json` |
| `x7` | The size of one posted signature; the prototypes' times | `experiments/X7/results/x7.json` |
| `x2a` | The bytes of the real cases, binary and hex JSON | `experiments/X2a/results/sizes.json` |
| `xc4` | The CKB IDL documents, rebuilt byte for byte | the documents in `experiments/XC4/idl/` |
| `xrt2` | The first round's offline rule checks | `experiments/XRT/results/prototype-checks.json` |
| `xrtb2` | The second round's offline rule checks, with keys made at run time | `experiments/XRTb/results/rule-checks.json` |
| `x6` | The size of each wallet's diff (files, lines added and removed, code lines) | `experiments/X6/results/measure.json` |

`--only x2,x3` runs a subset; `--out DIR` writes the results somewhere other than `bench/out/`.

## The output

A table on the screen, and in `bench/out/`: `summary.md` (the same table), `summary.json`, and each benchmark's raw output. Each row has a status:
- **PASS:** a deterministic value (a count, a byte size, a byte-for-byte round trip, an outcome) equals the recorded one;
- **FAIL:** it doesn't (the runner then exits with status 1);
- **INFO:** a time, measured on your machine, shown next to the recorded one for reference only; or a note, such as fewer trials than recorded;
- **SKIP:** the input isn't in this checkout, with the step that adds it.

## The mainnet inputs

Two real cases, fiber-scripts PR #34 (R1) and a 2-of-3 genesis multisig payment on mainnet (R2), are public mainnet data that this branch doesn't hold. Without them, their benchmarks show SKIP. To add them:

```sh
./bench/fetch-mainnet.sh
```

It reads CKB's public mainnet RPC and GitHub at pinned versions, read-only, checks every transaction hash and every file's SHA-256, and rebuilds the case files ([experiments/mainnet-inputs.md](../experiments/mainnet-inputs.md)). This is the only step that uses the network.

## Optional steps that need more

**The wallet diffs against their upstream source.** `./bench/wallets.sh` clones ckb-cli, CCC and Neuron at their pinned commits into `refs/` (if they aren't there yet), applies each diff to a pristine copy, and counts it. Building each wallet and running its own tests before and after is described in [experiments/X6/README.md](../experiments/X6/README.md).

**The devnet benchmarks** (X1's mixed-tool transactions, X4's high-s twins on chain and its replays, X5's seven end-to-end flows, XRT-1, XRT-3 and XRT-4, XRTb-1 and the Nervos DAO withdrawal of XRTb-3, and XQ14 on Ledger's emulator) need a local dev chain, fresh test keys, and for X5, X7 and XRT-4 the patched wallets. The outline:

1. **Keys outside the checkout, made at run time:** `ln -s "$(mktemp -d)" keys` at the repository root. The scripts write test keys only there (they refuse a path inside the checkout), and git ignores `keys`. Delete the temporary folder when you're done.
2. **The 2024 and v2 multisig binaries**, which the devnet copies from mainnet: `cd experiments/X1 && python3 -I -X utf8 scripts/fetch_mainnet.py`.
3. **A local dev chain**, made with the CKB node's own `ckb init --chain dev`, then given the three multisig deployments and the test keys' cells by `scripts/devnet_setup.py`: [experiments/X1/README.md](../experiments/X1/README.md), steps 1 and 2. Run `ckb run -C devnet/node` and `ckb miner -C devnet/node` (ckb 0.210.0).
4. **Each experiment's own commands**, in its README. For example, the on-chain high-s twins: fund the cells with `experiments/X5/scripts/fund_s4.py`, then `cd experiments/X4 && python3 -I -X utf8 scripts/high_s_devnet.py`.

## Rules the runner follows

- No keys, seeds or chain data are written into the tree; every key it makes lives in memory only.
- No network access, except `fetch-mainnet.sh` and `wallets.sh`, which fetch public sources at pinned versions and only when you run them.
- Nothing outside the checkout is written, apart from temporary files it deletes; nothing needs sudo.
