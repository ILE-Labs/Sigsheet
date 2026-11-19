# Experiments

Each experiment has a README with its question, method and exact commands, and a `results.md` that opens with its conditions. Raw output is in each `results/` folder. **Every number is design-stage:** measured on the throwaway prototypes in [`prototypes/`](prototypes/README.md) and on patched copies of the wallets ([X6](X6/README.md)).

| Experiment | Question | Runs offline with `./bench/run.sh` |
|---|---|---|
| [X1](X1/README.md) | Do ckb-cli, Neuron and CCC compute the same signing message? | The independent implementation's messages |
| [X2](X2/README.md) | Does each format round-trip every case; does C map onto CoBuild's building packet; what does a signer's message read? | Yes |
| [X2a](X2a/README.md) | How many bytes do the real cases take, binary and hex JSON? | Yes, with the mainnet inputs |
| [X3](X3/README.md) | Is merging safe in any order, any number of times, with junk? | Yes (on offline copies of its devnet cases) |
| [X3a](X3a/README.md) | Which merge rule is order-independent on PR #34's real signatures? | The four rules, with the mainnet inputs; CCC's merge needs Node |
| [X4](X4/README.md) | Is each attack caught? Does the lock accept a high-s twin on chain? | The attacks, with the mainnet inputs; the on-chain part needs a devnet |
| [X5](X5/README.md) | G1 and G2 end to end: three wallets, one shared file, no collector | No: a devnet and the patched wallets |
| [X6](X6/README.md) | What does adoption cost in each wallet? | The line counts of the diffs; building and testing the wallets is an optional step |
| [X7](X7/README.md) | Sizes, times and limits | Sizes and prototype times; the wallets' times need their builds |
| [XC4](XC4/README.md) | Can CKB IDL describe and bind the multisig witness; what does reuse cost? | The IDL documents' bytes; decoding needs the Rust harness |
| [XQ14](XQ14/README.md) | Can a Ledger sign a Sigsheet multisig transaction (on Ledger's emulator)? | No: the emulator and a devnet |
| [XRT](XRT/README.md) | Attacks and objections, first round | XRT-2; the rest needs a devnet |
| [XRTb](XRTb/README.md) | Attacks and objections, second round | XRTb-2; the rest needs a devnet |

## What isn't in this branch, and the local folders that replace it

The experiments ran against things a public repository shouldn't hold. The scripts expect them in four folders at the repository root, all git-ignored (see the root `.gitignore`):

| Folder | What it holds | How to make it |
|---|---|---|
| `keys/` | Fresh test keys. The devnet experiments make them with [`X1/scripts/keygen.py`](X1/scripts/keygen.py) and read them from `keys/<experiment>/` | Make `keys` a link to a temporary folder outside the checkout, so no key file is ever inside it: `ln -s "$(mktemp -d)" keys`. Delete that folder when you're done. Never use real keys |
| `refs/` | Clones of the upstream repositories at the pinned commits in [sources.md](../sources.md), and package caches (`refs/_npm-cache`, `refs/_cargo-home`) | `git clone <url> refs/<folder> && git -C refs/<folder> checkout <commit>` |
| `devnet/` | A local CKB devnet's data | [X1](X1/README.md), step 1 |
| the mainnet inputs | The real cases' transactions and files (R1, fiber-scripts PR #34; R2, a 2-of-3 genesis multisig payment on mainnet) | [mainnet-inputs.md](mainnet-inputs.md) |

Third-party code is never copied in: patched wallets, the emulator's change and test harnesses that start from upstream files are diffs against the pinned commits, with each project's license and copyright notice in a `NOTICE.md` next to the diff.

## Tools and versions

| Tool | Version used | Needed for |
|---|---|---|
| Python | 3.14.4 (standard library only) | Every script and the benchmark runner |
| Node | v22.22.1 (npm, and pnpm 11.8.0 via npx for CCC) | X1, X3a, X5, X6, X7, XQ14, XRT-4: CCC, Neuron and the Ledger host |
| Rust | rustc and cargo 1.100.0 (stable) | X1's Rust harness, X6, XC4, XRT-4: ckb-cli and CKB IDL |
| ckb, ckb-cli | `ckb 0.210.0 (2592ddf 2026-09-17)`, `ckb-cli 2.0.0 (80efc21 2025-12-03)` | Every devnet run |
| Speculos | 0.27.6 | XQ14 |

## Throwaway code

The prototypes and patches are experiment code, written to measure the design. They are not the specification and not a reference implementation; phase 1 writes those ([design record §8](../design-record.md#8-phase-1-sigsheet-v01-scope-and-acceptance-tests)).
