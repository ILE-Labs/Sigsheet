# X5: G1 and G2 end to end on the devnet

**Question (gates G1 and G2):** on a local devnet, with 2-of-3 and 3-of-5 multisigs, do signatures added in different orders by ckb-cli and CCC (and Neuron) to one shared file, with no single collector, finalize into transactions the chain accepts?

## Method

The tools are X6's patches of path C: ckb-cli v2.0.0 (`tx sigsheet-sign`, `sigsheet-merge`, `sigsheet-send`), CCC 1.23.1 (`ccc.Sigsheet`, driven by `../X6/ccc/harness/sigsheet-ccc.ts`) and Neuron v0.204.1 (its own `TransactionSender.signMultisig`, run in Node by the jest harness `tests/x6/x6-sigsheet.test.ts`, which mocks only the wallet's storage, as X1 did). Each signs with its own signing code and a fresh test key. The Python prototype writes the unsigned files (any tool could) and, in two flows, acts as a fourth signer or as "anyone" who merges.

`scripts/x5.py` runs seven flows; every step's file is kept as `results/<flow>/NN-<step>.json`, with its SHA-256 in `results/x5-*.json`:

| Flow | Lock | Signers, in order | Gathering |
|---|---|---|---|
| F1 | v2 2-of-3 | ckb-cli (s1), then CCC (s2), who finalizes | one file passed along |
| F2 | v2 3-of-5 | ckb-cli (s5), CCC (s1), Neuron (s3), Python (s4), each on its own copy | copies posted to a shared folder; merged by ckb-cli, by CCC (reverse order) and by Python (another order); ckb-cli finalizes |
| F3 | genesis 2-of-3 | Neuron (s2), then ckb-cli (s3), who finalizes | passed along |
| F4 | v2 2-of-3, a witness beyond the inputs | Neuron (s3), then CCC (s1) | passed along |
| F5 | v2 2-of-3 + a single-key input (PR #34's shape) | ckb-cli (the single-key input, s4), CCC (s1), Neuron (s2), each on its own copy | merged by Python; CCC finalizes |
| F6 | v2 3-of-5, R = 1 (s1 must sign) | CCC (s2), ckb-cli (s3), Neuron (s4); finalizing refused; then ckb-cli (s1) | copies merged by ckb-cli; then passed along |
| F7 | 2024 deployment 2-of-3 | CCC (s1), ckb-cli (s2: it can't sign this lock), CCC (s3) | passed along |

The cells were funded from the devnet miner's key (`scripts/fund_s4.py`, `scripts/fund_more.py`; the funding record is `data/funding.json`).

## Exact commands

From `experiments/X5/`. Needs: X1's devnet running (X1 README, step 1); fresh test keys s0-s7 in `keys/s4/` at the repository root (`mkdir -p ../../keys/s4 && python3 -I ../X1/scripts/keygen.py 8 ../../keys/s4/keys.json s`), with `keys` a link to a temporary folder outside the checkout (keygen.py refuses to write inside it); an empty ckb-cli home for the patched ckb-cli in `keys/ckb-cli-home-s4`; and the X6 patched tools built ([X6 README](../X6/README.md)), including Neuron's harness (`sh ../X6/neuron/harness/make_harness.sh ../X6/neuron/packages/neuron-wallet`).

```sh
python3 -I -X utf8 scripts/fund_s4.py                                   # once
python3 -I -X utf8 scripts/fund_more.py A23V=6 A23G=3 B35V=3 B35VR=2 A23B=1
python3 -I -X utf8 scripts/x5.py f1_pass_along_2of3_v2 > results/x5-f1.json
python3 -I -X utf8 scripts/x5.py f2_parallel_3of5_v2_four_signers f3_genesis_neuron_then_ckbcli \
  f4_extra_witness_neuron_ccc f5_multisig_plus_single_key f6_first_r f7_2024_ccc_only > results/x5-f2-f7.json
```

Set `TMPDIR` to a folder you can delete afterwards: the CCC and Neuron runs write caches there, and Neuron's code writes its logs under `~/.config/Neuron`, which you may want to remove after the run.

## Environment

2026-11-18 (UTC); the local devnet (ckb 0.210.0); ckb-cli built from the patched copy (debug, rustc 1.100.0); CCC's patched core run by tsx 4.20.6 on Node v22.22.1; Neuron's patched wallet code under jest with X1's dependency install.

## Files

`scripts/` (`fund_s4.py`, `fund_more.py`, `x5.py`), `data/` (the funding records and two funding transactions), `results/` (every flow's files, `x5-f1.json`, `x5-f2-f7.json`), `results.md`.

The devnet transactions in `data/` and `results/` are records of what the flows sent to a private local chain, made with test keys that were never stored here; they hold no key.
