# XC4: can CKB IDL describe, decode and bind the existing multisig witness?

A check of the CKB IDL claims under gate C4: the framing (Sigsheet carries a partly signed transaction; CKB IDL describes what a script's witness must contain) is to be proven, not assumed, and reusing CKB IDL for the multisig witness is to be compared with defining the layout in Sigsheet. Every candidate path's C4 answer rests on these points, which the spec text alone can't settle.

## Questions

1. Can one CKB IDL 0.1.0 document describe the existing multisig witness lock (`S | R | M | N | N x 20-byte key hashes | M x 65-byte signatures`, [background §1](../../background.md#1-the-multisig-lock)), so that CKB IDL's own client decodes the real witnesses?
2. Could a client trust such a document for the existing deployments under CKB IDL's commitment rules (Binding Trailer 1)?
3. What would reuse cost, in bytes and in implementation size, against defining the layout in Sigsheet?

## Method

1. `scripts/extract_locks.py`: take every multisig `WitnessArgs.lock` from X1's saved transactions: fiber-scripts PR #34 as committed on mainnet, the genesis 2-of-3 payment (R2), and the 10 committed devnet cases. A lock counts as multisig when S = 0 and its length is exactly `4 + 20N + 65M`, the lock's own size rule. That gives 13 locks: 11 of 2-of-3 (two with R = 1) and 2 of 3-of-5.
2. `scripts/make_idls.py`: write candidate IDL documents as RFC 8785 canonical JSON:
   - `generic`: the natural description, four `uint8` fields, then `vector<bytes_fixed_20>` and `vector<secp256k1_sig>`;
   - `fixed-2of3`, `fixed-3of5`: one document per (M, N);
   - `union-n3`, `union-n5`, `union-n6`: a union whose u32 LE tag is the four header bytes read as one integer, with one variant per (R, M, N) for every N up to 3, 5 or 6.
3. `harness/`: a Rust program on `ckb-idl-client` (by path, at the pinned commit). For each document it checks canonical bytes, then runs `parse_document`, `IdlDocument::validate` and `decode_lock_witness` on all 13 locks. For each deployed code cell, it runs `verify_commitment`, which looks for Binding Trailer 1.
4. `ckb-idl validate` (the CLI at its pinned commit, built with its own `Cargo.lock`) on every document. `ckb-idl inspect` on the three deployed code cells.
5. `ckb-idl bind` on the v2 code cell with `union-n5`, then `scripts/binding_check.py`. It computes each code cell's data hash and the bound cell's data hash, and reads the lock of each deployed code cell from X1's mainnet record.
6. `scripts/measure_loc.py`: count the lines of the IDL client, and of the multisig witness code that ckb-sdk (used by ckb-cli), CCC and Neuron already have.
7. npm and crates.io lookups for published CKB IDL packages (read-only GETs).

## Exact commands

From `experiments/XC4/`:

```sh
python3 -I -X utf8 scripts/extract_locks.py > results/locks.json
python3 -I -X utf8 scripts/make_idls.py | tee results/idl-sizes.txt
(cd harness && CARGO_HOME=$PWD/../../../refs/_cargo-home cargo build --release) > results/harness-build.log 2>&1
B=../X1/data/mainnet
./harness/target/release/xc4-idl-harness results/locks.json idl/generic.json idl/fixed-2of3.json idl/fixed-3of5.json \
  idl/union-n3.json idl/union-n5.json idl/union-n6.json -- $B/multisig-genesis.bin $B/multisig-2024.bin $B/multisig-v2.bin \
  > results/harness-output.jsonl
# the CLI, from its pinned clone, with its own lockfile, built outside the clone:
(cd ../../refs/ckb-idl/ckb-idl-cli && CARGO_HOME=$OLDPWD/../../refs/_cargo-home \
  cargo build --release --locked --target-dir $OLDPWD/cli/target) > results/cli-build.log 2>&1
for f in idl/*.json; do ./cli/target/release/ckb-idl validate --idl $f; done > results/cli-validate.txt 2>&1
for b in genesis 2024 v2; do ./cli/target/release/ckb-idl inspect --executable $B/multisig-$b.bin; done > results/cli-inspect.txt 2>&1
./cli/target/release/ckb-idl bind --executable $B/multisig-v2.bin --idl idl/union-n5.json --out-dir results/bind-sim/v2
python3 -I -X utf8 scripts/binding_check.py > results/binding-check.json
python3 -I -X utf8 scripts/measure_loc.py > results/loc.json
# package lookups (2026-11-18): npm view <name> for ckb-idl, ckb-idl-client, @ckb-idl/client, @ckb-idl/core,
# ckb-idl-derive-ts, @ckb-idl/derive-ts, idl-derive-ts; npm search ckb-idl;
# curl https://crates.io/api/v1/crates/<name> for ckb-idl-client, -cli, -derive, -types, -export
```

`results/cli-validate.txt` and `results/cli-inspect.txt` hold the outputs as the loop printed them, with exit codes.

## Environment and versions

- 2026-11-18 (UTC), on a Linux machine with 2 CPUs; rustc and cargo 1.100.0; Python 3.14.
- `ckb-idl-client` at `e7d8124921dc640018004a4a031fc6146535e334` (by path; the harness uses its `Cargo.toml` dependencies resolved on 2026-11-18). `ckb-idl-cli` at `c5fb2d728f1e6e09321401d85f03e7213272d1a8`, built `--locked` with its own `Cargo.lock`, which pins `ckb-idl-client` 0.1.0 from crates.io (checksum `ccec25c3…a5c`). `ckb-idl-spec` at `ebec1696b3df3336262c479650611bb344489f01` (schema, encoding, limits, commitment).
- The deployed code cells are X1's copies of mainnet data (`experiments/X1/data/mainnet/multisig-*.bin`, fetched from `https://mainnet.ckb.dev/` on 2026-11-18). Their data hashes match X1's record; `binding_check.py` recomputes them.
- Wallet code for the line counts: ckb-sdk-rust `3a418e7` (v5.0.0), CCC `7095cca` (1.23.1), Neuron `d3a7467` (v0.204.1).

## Files

- `scripts/`: the four Python steps.
- `harness/`: the Rust harness (`Cargo.toml`, `src/main.rs`); `harness/target/` and `cli/target/` are build output, git-ignored and not in this branch.
- `idl/`: the six candidate documents, byte for byte as tested.
- `results/`: raw outputs (`locks.json`, `idl-sizes.txt`, `harness-output.jsonl`, `cli-validate.txt`, `cli-inspect.txt`, `bind-sim/` with `bind-output.txt` and the binding record (the bound binary itself, a copy of the mainnet v2 binary with a trailer, isn't kept), `binding-check.json`, `loc.json`, `packages.txt` for the npm and crates.io lookups, build logs).
- `results.md`: the answers and numbers.
