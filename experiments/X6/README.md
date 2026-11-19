# X6: what adoption costs in ckb-cli, CCC and Neuron (and what reusing CKB IDL would cost)

**Questions:**
1. What is the smallest local patch to each wallet that reads and writes path C, signs with the wallet's own signing code, merges and finalizes? Which files and functions does it hook into, how many lines does it add, and do the wallet's own tests still pass?
2. What does path A (the building-packet profile) add on top of that, measured in one wallet; and how does B compare?
3. The CKB IDL reuse alternative, where it can be measured: what would adding CKB IDL's client cost a wallet?

**Answer** (design-stage; [results.md](results.md)): ckb-cli +415 lines (381 code), CCC +260 (229), Neuron +153 / −2 (137); each wallet's own tests give the same results before and after.

The patches are throwaway, made in copies of the pinned commits. Nothing was proposed to any project. This branch holds them only as diffs, each with the upstream project's license and copyright notice in a `NOTICE.md` next to it.

## The diffs

| Wallet | Pinned source | Diff | Apply it in | License notice |
|---|---|---|---|---|
| ckb-cli | v2.0.0 `80efc21c30e9fc7847407a217034681b6e46c763` | [`ckb-cli/patch.diff`](ckb-cli/patch.diff): `src/utils/sigsheet.rs` (new), `src/subcommands/tx.rs`, `src/utils/mod.rs` | the checkout's root | [`ckb-cli/NOTICE.md`](ckb-cli/NOTICE.md) |
| CCC | `@ckb-ccc/core` 1.23.1 `7095ccad564b94ea2e59284cb4a364aa3499252e` | [`ccc/patch.diff`](ccc/patch.diff): `src/sigsheet/index.ts` (path C, new), `src/sigsheet/buildingPacket.ts` (path A, new), `src/barrel.ts` | `packages/core` | [`ccc/NOTICE.md`](ccc/NOTICE.md) |
| Neuron | v0.204.1 `d3a7467d218e4b6f777326682a83fec802669c00` | [`neuron/patch.diff`](neuron/patch.diff): `src/utils/sigsheet.ts` (new), `src/services/transaction-sender.ts` | `packages/neuron-wallet` | [`neuron/NOTICE.md`](neuron/NOTICE.md) |

Each diff's paths are relative to the folder in the fourth column; apply it there with `patch -p1 < <diff>` (or `git apply`). The diffs were regenerated for publication from the measured copies; four doc comments were reworded (no code line changed, and the counts are the same).

`measure.py` counts each patch: it re-extracts a pristine copy of each wallet with `git archive` from a clone in `refs/` at the pinned commit, writes each `patch.diff` from the patched copy, and counts lines ("code lines": added lines that are neither blank nor comment-only). `./bench/run.sh` (benchmark `x6`) counts the published diffs the same way, offline, and compares them with `results/measure.json`.

## Exact commands

From the repository root. The patched copies live at the paths below, which X5, X7 and XRT also use; they are git-ignored.

```sh
# Clones at the pinned commits (sources.md)
git clone https://github.com/nervosnetwork/ckb-cli refs/ckb-cli && git -C refs/ckb-cli checkout 80efc21c30e9fc7847407a217034681b6e46c763
git clone https://github.com/ckb-devrel/ccc refs/ccc && git -C refs/ccc checkout 7095ccad564b94ea2e59284cb4a364aa3499252e
git clone https://github.com/nervosnetwork/neuron refs/neuron && git -C refs/neuron checkout d3a7467d218e4b6f777326682a83fec802669c00

# ckb-cli: copy, baseline tests, patch, build, tests again (the system's stable toolchain, not the clone's pin)
mkdir -p experiments/X6/ckb-cli/src-copy && git -C refs/ckb-cli archive 80efc21c30e9fc7847407a217034681b6e46c763 | tar -x -C experiments/X6/ckb-cli/src-copy
sh experiments/X6/ckb-cli/test.sh baseline-cargo-test
(cd experiments/X6/ckb-cli/src-copy && patch -p1 < ../patch.diff)
(cd experiments/X6/ckb-cli/src-copy && RUSTUP_TOOLCHAIN=stable CARGO_HOME=$PWD/../../../../refs/_cargo-home cargo build --locked)
sh experiments/X6/ckb-cli/test.sh patched-cargo-test

# CCC: copy packages/core, install its dependencies with pnpm 11.8.0 (CCC's package manager; npm fails on its aliases)
mkdir -p experiments/X6/ccc/core && git -C refs/ccc archive 7095ccad564b94ea2e59284cb4a364aa3499252e packages/core | tar -x -C experiments/X6/ccc/core --strip-components=2
(cd experiments/X6/ccc/core && npm_config_cache=$PWD/../../../../refs/_npm-cache npx -y pnpm@11.8.0 install --ignore-scripts --store-dir $PWD/../../../../refs/_pnpm-store)
(cd experiments/X6/ccc/core && ./node_modules/.bin/vitest run > ../results/baseline-vitest.log)
(cd experiments/X6/ccc/core && patch -p1 < ../patch.diff)
(cd experiments/X6/ccc/core && ./node_modules/.bin/tsc --noEmit -p tsconfig.json && ./node_modules/.bin/vitest run > ../results/patched-vitest.log)
(cd experiments/X6/interop && python3 -I -X utf8 make_a_check.py)       # interop/a-check/: the X2 cases as C and A files
(cd experiments/X6/ccc/harness && npm install && npx tsx a-codec.ts ../../interop/a-check > ../../results/ccc-a-codec-vs-python.json)

# Neuron: copy the wallet package and root configs, install dependencies, baseline tests, patch, tests again
git -C refs/neuron archive d3a7467d218e4b6f777326682a83fec802669c00 packages/neuron-wallet tsconfig.json jest.config.js package.json | tar -x -C experiments/X6/neuron
(cd experiments/X6/neuron && npm_config_cache=$PWD/../../../refs/_npm-cache YARN_CACHE_FOLDER=$PWD/../../../refs/_yarn-cache \
  ELECTRON_SKIP_BINARY_DOWNLOAD=1 npx yarn@1.22.22 install --frozen-lockfile --ignore-scripts)
sh experiments/X6/neuron/test.sh baseline-relevant
(cd experiments/X6/neuron/packages/neuron-wallet && patch -p1 < ../../patch.diff)
sh experiments/X6/neuron/test.sh patched-relevant
(cd experiments/X6/neuron/harness && sh make_harness.sh ../packages/neuron-wallet)   # tests/x6/x6-sigsheet.test.ts, for X5

# Measure, and the CKB IDL dependency check
(cd experiments/X6 && python3 -I -X utf8 measure.py > results/measure.json)
#   ckb-cli-idl/: a fresh copy of ckb-cli with `ckb-idl-client = "0.1.0"` added to Cargo.toml; `cargo tree -e normal
#   --prefix none` before (--locked) and after; then the copy is deleted, keeping idl-dependency.diff and the crate lists.
```

Tests run: ckb-cli `cargo test --locked` (its root crate's unit tests); CCC core's whole vitest suite (36 files); Neuron's ten test files for the modules the patch touches (`neuron/test.sh` lists them). Neuron's Electron binary is never downloaded (`--ignore-scripts`); `ELECTRON_OVERRIDE_DIST_PATH` lets `require('electron')` return a path instead of throwing, without writing anything. Its SQLite native module isn't built either, which fails one suite the same way before and after.

The measured run installed Neuron's dependencies once, in X1's Neuron checkout, and linked this copy's `node_modules` to them; installing them in place, as above, gives the same dependency versions (Neuron's `yarn.lock`).

## Environment

2026-11-18 (UTC); rustc and cargo 1.100.0 (stable); Node v22.22.1; pnpm 11.8.0 (via npx); CCC core's dependencies as its `pnpm-lock.yaml` records; Neuron's from its `yarn.lock`; ckb-cli's from its `Cargo.lock`.

## Files

- `ckb-cli/`, `ccc/`, `neuron/`: each wallet's `patch.diff` and `NOTICE.md`, its test script (`test.sh`), and its test logs (`results/`).
- `ccc/harness/`: `sigsheet-ccc.ts`, the command-line driver X5 and X7 use, and `a-codec.ts`, the path A cross-check. Its `package.json` pins tsx 4.20.6; the measured run's lockfile isn't kept.
- `neuron/harness/`: `x6-sigsheet.test.diff` and `make_harness.sh`, which rebuild the jest harness X5 uses from Neuron's own `transaction-sender.test.ts` (its `NOTICE.md` names Neuron's license).
- `ckb-cli-idl/`: the CKB IDL dependency check (`idl-dependency.diff`, the crate lists, `NOTICE.md`).
- `interop/`: files the interop checks use. `a-check/` holds the X2 cases as C files (`*.c.json`) and A building packets (`*.a.hex`), written by `interop/make_a_check.py`; CCC's path A layer is checked against them, and XRT-2 reads the C files. `k-s1.json`, `k-s2.json`, `k-m.json` and `k-final.json` are ckb-cli's files from the byte-identity check in [results §3](results.md#3-the-three-patches-read-and-write-the-same-bytes) (signed by s1, by s2, merged, finalized), and `n-s3.json` is Neuron's file signed by s3; CCC's counterparts weren't kept. R1 and R2 in `a-check/` are mainnet inputs ([mainnet-inputs.md](../mainnet-inputs.md)).
- `results/`: `measure.json`, `ccc-a-codec-vs-python.json`.
- `measure.py`.
