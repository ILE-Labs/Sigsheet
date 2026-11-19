# X6 results: what adoption costs, measured in the three wallets

Conditions (design-stage): 2026-11-18 (UTC); throwaway patches made in copies of ckb-cli v2.0.0 (`80efc21`), CCC `@ckb-ccc/core` 1.23.1 (`7095cca`) and Neuron v0.204.1 (`d3a7467`); nothing proposed to any project. Diffs: `<wallet>/patch.diff`; counts: `results/measure.json`; test logs: `<wallet>/results/` and `results/`. Commands: `README.md`.

## 1. Path C in each wallet: the patch, its hook points, its size

| Wallet | Files changed | Lines added (code lines) | Hook points (what the patch calls, unchanged) | What it does |
|---|---|---|---|---|
| **ckb-cli** | 3 | **+415 (381)**: `src/utils/sigsheet.rs` +345 (312), `src/subcommands/tx.rs` +69 (68), `src/utils/mod.rs` +1 | `tx_helper::build_signature` (ckb-cli's message rule), `SignerFn` from `get_privkey_signer` or `get_keystore_signer` (key file, keystore or plugin), ckb-sdk's `MultisigConfig::to_witness_data` | `tx sigsheet-sign`, `sigsheet-merge`, `sigsheet-send` (finalize, then send or write); they run before ckb-cli's node check, so signing and merging work offline |
| **CCC** | 2 | **+260 (229)**: `src/sigsheet/index.ts` +259 (228), `src/barrel.ts` +1 | `SignerMultisigCkbPrivateKey.signOnlyTransaction`, `SignerMultisigCkbReadonly.getSignInfo`, `SignerCkbPrivateKey`, `Transaction.getSignHashInfo`, `MultisigCkbWitness`, `JsonRpcTransformers`, `recoverMessageSecp256k1`, the client cache | `ccc.Sigsheet`: read, sign, merge, finalize; the input cells come from the file into the client's cache, so it works offline |
| **Neuron** | 2 | **+153 / −2 (137)**: `src/utils/sigsheet.ts` +145 (129), `src/services/transaction-sender.ts` +8 / −2 | `TransactionSender.signMultisig` (Neuron's own signing, and its Ledger path, which now gets the file's previous transactions as `context`), `MultisigConfigModel`, the chain models | Reads a file into Neuron's models and writes the signatures Neuron adds back; fixes `signMultisig` so witnesses beyond the inputs are signed and kept (X1's S9 bug) |

Not measured: user interface work (Neuron's renderer, `neuron-ui`, and its IPC controller; CCC has no UI; ckb-cli's are the subcommands above). None of the three patches adds code for the multisig witness layout: each reuses the wallet's existing codec (ckb-sdk's `MultisigConfig`, CCC's `MultisigCkbWitness`, Neuron's `Multisig.serialize`).

## 2. Their own tests, before and after

| Wallet | Tests run | Before | After |
|---|---|---|---|
| ckb-cli | `cargo test --locked` (its unit tests) | 7 passed | **7 passed** |
| CCC | core's whole vitest suite (36 files) | 759 passed | **759 passed** (and `tsc --noEmit` clean) |
| Neuron | the 10 test files for the modules touched (`neuron/test.sh`) | 103 passed, 24 failed, 1 skipped | **the same 103 passed, the same 24 failed**, 1 skipped |

Neuron's 24 failures are all in `tests/services/multisig.test.ts`, which needs the SQLite native module that X1's install didn't build (`DriverPackageNotInstalledError`); the list of failing tests is identical before and after (`neuron/results/baseline-relevant.log`, `patched-relevant.log`).

## 3. The three patches read and write the same bytes

- ckb-cli's file after signing with s1 is **byte-identical** to CCC's file after signing with s1; ckb-cli's merge of its own s1 file and CCC's s2 file is byte-identical to CCC's merge of its own two (ckb-cli's files are in `interop/`: `k-s1.json`, `k-s2.json`, `k-m.json`, `k-final.json`; CCC's weren't kept). The final transactions have the same hash and witnesses.
- The Python prototype's strict reader (schema and canonical form) accepts every file each wallet wrote (X5).
- **A canonical-form detail the spec must fix:** CCC's `JsonRpcTransformers.transactionFrom` leaves out `type` when an output has none, where ckb-cli and the prototype write `"type": null`. The patches never re-render the file's transaction, so the files stay identical, but the spec must say which form is canonical, so that a tool which rebuilds the transaction JSON writes the same bytes.

## 4. What path A adds on top of C (measured in CCC), and how B compares

- **A in CCC: +103 lines (95 code)**, `src/sigsheet/buildingPacket.ts`: the Molecule codecs for `BuildingPacket`, `MultisigAction` and `ScriptInfo` with CCC's `mol` helpers, the C-to-A mapping, and A's profile checks (`message` empty, `change_output` none, `resolved_inputs` equal to the previous transactions). Its packets are **byte-identical to the Python prototype's on all 12 X2 cases** (`results/ccc-a-codec-vs-python.json`): two implementations of the profile agree.
- **CCC is the easy case for A:** it has a generic Molecule library, and its `@ckb-ccc/spore` package already defines a `BuildingPacket` codec (`buildingPacket.ts`, in the CoBuild folder of the package's [`codec` folder](https://github.com/ckb-devrel/ccc/tree/7095ccad564b94ea2e59284cb4a364aa3499252e/packages/spore/src/codec)). ckb-cli (with ckb-sdk) and Neuron have no `BuildingPacket` code at all (searched at the pinned commits); for Rust, the generated Molecule code for CoBuild's types in cryptape's proof of concept is 5,200 lines (the generated `src/schemas/basic.rs` of the proof of concept's `ckb-transaction-cobuild` crate, at `e29514f`).
- **B (not patched):** in the prototypes, the format layer is 63 code lines for C, 98 for B and 199 for A, on a shared core of 350; B and A also need Molecule decoding of whole transactions (77 lines), which the wallets have for their own types. B's per-input layout adds the mapping from groups to inputs, and as revised it can't carry witnesses (X2).

## 5. The CKB IDL reuse alternative, where it can be measured

| | Reuse CKB IDL for the multisig witness | Path C's patches, as measured |
|---|---|---|
| Layout code a wallet adds | An IDL client: `ckb-idl-client` is 1,318 Rust code lines (XC4) | 0 new lines: each patch reuses the wallet's existing multisig codec |
| ckb-cli's dependencies | Adding `ckb-idl-client = "0.1.0"` to ckb-cli v2.0.0 adds **29 crate versions** to its normal dependency graph (391 → 417 unique) and moves 3 shared ones to newer versions; `Cargo.lock` +401 / −31 lines (`ckb-cli-idl/`) | none |
| CCC and Neuron (TypeScript) | Not measurable: no CKB IDL client is published for TypeScript (XC4's npm lookups); planned for CKB IDL's milestone M4 | none |
| Bytes per file | 18,372 for the N ≤ 5 union document, or a digest that needs a lookup (XC4) | 0 |

So the efficiency comparison holds on the measurement: the Sigsheet code each wallet needs (137-381 code lines) is code for the file itself (reading, signing through the wallet's own signer, merging, finalizing); none of it describes the witness layout, which is the part CKB IDL could have supplied, and supplying it through CKB IDL would add a dependency, not remove code.

## Answer

Adopting path C costs a patch of 137 code lines in Neuron, 229 in CCC and 381 in ckb-cli at the pinned commits, each using the wallet's own signing code; every wallet's own tests give the same results before and after. Path A adds about 95 code lines even in CCC, which already has the Molecule tools, and much more in ckb-cli and Neuron, which have no CoBuild code. Reusing CKB IDL for the witness layout would replace no code and add 29 crates to ckb-cli; for TypeScript it isn't possible yet.
