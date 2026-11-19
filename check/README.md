# The independent check

Confirms the vectors with code that isn't the generator's: CCC's, ckb-cli's and ckb-sdk's own message code, and the
deployed lock binaries. Each check reads `vectors/` only and never imports the generator.

| Check | What it confirms | Pinned |
|---|---|---|
| `ccc/` | For every vector: each lock group, found again from the file's context, matches `expected.json`; each group's message, computed by CCC (`SignerMultisigCkbReadonly.getSignInfo` for multisig, which also derives the lock args from the config; `Transaction.getSignHashInfo` for the single-key lock, after `prepareSighashAllWitness` as CCC's own signer does), equals `expected.json`'s; every kept signature recovers (`recoverMessageSecp256k1`) to the member it is filed under, and every dropped one doesn't. Offline: input cells go into CCC's client cache, and the client's RPC URL is a closed local port | `@ckb-ccc/core` 1.23.1 with `package-lock.json`; TypeScript 7.0.2, prettier 3.9.10 and `@types/node` 22.7.5 for development; Node 22.22.1 |
| `ckb-sdk/` | Each group's message, computed by ckb-cli v2.0.0's `build_signature` (copied verbatim, `src/ckb_cli_build_signature.rs`, MIT, see `NOTICE.md`) and by ckb-sdk's own script signers through `ScriptSigner::sign_tx`, equals `expected.json`'s | `ckb-sdk` 5.0.0 with ckb-cli v2.0.0's `Cargo.lock`, which cargo trimmed to this crate's packages; Rust 1.100.0 |
| `locks/` | Every final transaction's signed lock groups pass the deployed lock's own binary under ckb-debugger (`Run result: 0`); and the controls give the chain's verdicts: a high-s twin is accepted, S4N's set (without the required member) and the genesis sets the genesis binary rejects fail with `Run result: -52` | ckb-debugger v1.1.1 (release asset `ckb-debugger_v1.1.1_x86_64-unknown-linux-gnu.tar.gz`, SHA-256 `0dee02804af46386527c8bb94c2ee63592594ca1ec952ea42ffa9df07a9f005e`); the code cells in `locks/code-cells.json`, their data fetched read-only from mainnet and checked by data hash, never committed |

## Run

From the repository root, with `vectors/mainnet/.fetched` added to each list after `fetch-mainnet`:

```sh
(cd check/ccc && npm ci --ignore-scripts && npx tsc --strict --types node --target es2022 --module nodenext --moduleResolution nodenext --outDir dist messages.ts && npx prettier --check messages.ts package.json)
node check/ccc/dist/messages.js vectors

(cd check/ckb-sdk && cargo fmt --check && cargo clippy --locked -- -D warnings && cargo build --locked --release)
check/ckb-sdk/target/release/check-ckb-sdk vectors

python check/locks/run.py --debugger <path to ckb-debugger> vectors
```

`check/locks` keeps the fetched binaries in `check/locks/.work/`, which git ignores; a second run needs no network.
Each check prints one summary line and exits with 1 on any problem.
