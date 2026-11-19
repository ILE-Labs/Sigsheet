# The mainnet inputs

Two real mainnet transactions are test cases here: **R1**, the fiber-scripts PR #34 contract upgrade (a 3-of-5 v2 multisig next to a single-key input), and **R2**, a 2-of-3 genesis multisig payment on mainnet. Their transactions, the PR #34 deploy file and its four signature comments, and the files built from them aren't in this branch. They are public: anyone can fetch them, and every file is checked when it's fetched.

## Get them

```sh
./bench/fetch-mainnet.sh
```

It reads, with a generic User-Agent and nothing but read-only calls:
- **CKB mainnet JSON-RPC** at `https://mainnet.ckb.dev/` (the public endpoint [docs.nervos.org](https://github.com/nervosnetwork/docs.nervos.org/blob/6a6152f4e424353032eac41864350b948efad913/website/docs/getting-started/rpcs.mdx) lists; `--rpc URL` picks another): the transactions below. Each transaction hash is recomputed with [`X1/scripts/ckbcore.py`](X1/scripts/ckbcore.py) and must match.
- **GitHub:** the deploy file `deployment/mainnet/mainnet.json` at fiber-scripts commit `026027f54f6a90cb48d8cc184b230e2018bb8611` (SHA-256 `8563ba8dcd0d051822dd0cc21db995dc8e6a2984e900d3500068f0185a07b51e`), and PR #34's four signature comments by id ([1](https://github.com/nervosnetwork/fiber-scripts/pull/34#issuecomment-6571892250), [2](https://github.com/nervosnetwork/fiber-scripts/pull/34#issuecomment-6573354672), [3](https://github.com/nervosnetwork/fiber-scripts/pull/34#issuecomment-6581601897), [4](https://github.com/nervosnetwork/fiber-scripts/pull/34#issuecomment-6605978601)).

Then it rebuilds the case files with the experiments' own scripts and checks each against [`mainnet-inputs.sha256`](mainnet-inputs.sha256), which records the SHA-256 of every file as the experiments used it. After that, `./bench/run.sh` runs the real cases too.

## What they are

| Input | What it is | Used by |
|---|---|---|
| The deploy file and the four PR comments | R1: PR #34's transaction (`cell_tx`), its input transactions, and the six real signatures | X1, X2 (R1 is replayed from these and must give the committed hash below), X2a, X3, X3a, X7, XQ14, XRT-2 |
| `0x4396de69818bd88b7fce64797ccec25d1294912d56846432f29fd192120992ee` | PR #34's transaction as committed (block 20,965,430) | X1 (the three signatures in its witness), XC4 |
| `0x63a7f3a52fc91c52939186ca9c1064238ccdfe498d3398f25707537f591bbaa4` | R2, the genesis 2-of-3 payment (block 20,354,743) | X1, X2, X2a, X4 (its base case), X7, XC4, XQ14, XRT-2 |
| `0x1565338fd543a257906e5debe6b4b5cedbe4cff86af47ec620e18a3bfb838b9a` | R2's previous transaction | X1, X2, X2a |
| the genesis block; `0x0a13d8d9…55d8`, `0x3e27a1a2…a282` (the 2024 and v2 code cells); `0x44be4f4f…dc60`, `0x6888aa39…f738` (their dep groups) | The three multisig deployments' binaries and dep groups | X1 (it copies the 2024 and v2 binaries into the devnet's genesis), XC4 (the binding checks) |

These last ones, and the record of where mainnet's multisig funds sit, come from X1's full fetch, [`X1/scripts/fetch_mainnet.py`](X1/scripts/fetch_mainnet.py), which the devnet experiments need anyway.

| File (in this branch's layout) | Made by |
|---|---|
| `X1/data/mainnet/*.json`, `*.bin` | `bench/fetch_mainnet.py` (the three transactions above) or `X1/scripts/fetch_mainnet.py` (all) |
| `X1/data/fiber-scripts-34/mainnet.json`, `comment-1.txt` … `comment-4.txt` | `bench/fetch_mainnet.py` |
| `X1/cases/R1-fiber-scripts-pr34.json`, `R2-dao-payout.json` | `X1/scripts/build_cases.py --real-only` |
| `X2/cases/R1-…`, `R2-…` | `prototypes/cases.py` |
| `X3a/results/partials.json` | `X3a/scripts/build_partials.py` |
| `X6/interop/a-check/R1-…`, `R2-…` | `X6/interop/make_a_check.py` |
| `XQ14/results/runs/pr34-replay-*`, `dao-payout-replay`, and their emulator logs | the XQ14 runs (the emulator and a devnet) |

The fetched records carry their fetch time, so their digests in `mainnet-inputs.sha256` are recorded as comments; the files rebuilt from them are byte-identical to the ones the experiments used, and the fetch checks that.
