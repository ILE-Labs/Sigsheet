# XC4 results: CKB IDL and the existing multisig witness

Conditions (design-stage): 2026-11-18 (UTC). The CKB IDL client is `ckb-idl-client` at e7d8124 and the CLI is `ckb-idl-cli` 0.1.0 at c5fb2d7, built with its own lockfile. Spec at ebec169. The inputs are 13 real multisig witness locks: PR #34 as committed on mainnet, the genesis 2-of-3 payment (R2), and 10 committed devnet cases from X1. The code cells are the three mainnet deployments, copied in X1. Commands are in `README.md` and raw output in `results/`.

## 1. Can one IDL 0.1.0 document describe the multisig witness? Only with a workaround, and only for small configurations

| Document | Canonical bytes | Valid (client and CLI) | Real locks decoded (of 13) | Why |
|---|---:|---|---:|---|
| `generic` (4 × `uint8`, `vector<bytes_fixed_20>`, `vector<secp256k1_sig>`) | 551 | yes | **0** | A `vector` starts with its own u32 LE count, and the multisig layout has none. The decoder reads key-hash bytes as the count, then runs out (`field_too_short`) |
| `fixed-2of3` | 591 | yes | 11 | Decodes 2-of-3 only. The two 3-of-5 locks fail with `trailing_bytes` |
| `fixed-3of5` | 683 | yes | 2 | Decodes 3-of-5 only. The 2-of-3 locks fail with `field_too_short` |
| `union-n3` (16 variants) | 4,670 | yes | 11 | The 3-of-5 locks fail with `unknown_union_tag` |
| `union-n5` (50 variants) | **18,372** | yes | **13** | Every real lock decodes |
| `union-n6` (77 variants) | 31,534 | yes (both tools) | 13 | Breaks the normative schema's cap of 64 variants per union, and the candidate limits of 20,480 bytes and 256 fields. Neither tool enforces them |

Sources: `results/harness-output.jsonl`, `results/cli-validate.txt`, `results/idl-sizes.txt`.

- **The natural description fails on every real witness.** `linear-0.1.0` has no field whose count comes from an earlier field. A `vector` carries its own u32 LE count, and `bytes` its own u32 LE length (ckb-idl-spec ebec169, `encoding/linear-0.1.0.md`). The multisig lock keeps its counts in header bytes 2 and 3 ([background §1](../../background.md#1-the-multisig-lock)).
- **One document per configuration works,** but an IDL is bound to a code cell, not to an address. So one document can't serve every multisig address under one deployment.
- **The union workaround:**
  - The union's u32 LE tag absorbs the four header bytes `S, R, M, N`, giving one variant per (R, M, N).
  - It covers every configuration with N ≤ 5: 50 variants, 18,372 bytes, 191 field entries. That fits the normative 64-variant cap and the candidate 20,480-byte limit.
  - N ≤ 6 needs 77 variants. The lock itself allows N up to 255.
  - The workaround also misuses the union tag: R, M and N come back only as a variant name, not as fields.

## 2. Can a client trust any such document for the existing deployments? No

| Deployment | Code cell | Data bytes | Ends in Binding Trailer 1 magic? | `ckb-idl inspect` | Lock on the code cell |
|---|---|---:|---|---|---|
| genesis (`type`) | `0xe2fb1998…ff5c:4` | 52,424 | no (last 8 bytes `0000000000000000`) | `invalid_trailer` | code hash `0x00…00`, `data`, args `0x` |
| 2024 (`type`) | `0x0a13d8d9…55d8:0` | 52,424 | no (`0000000000000000`) | `invalid_trailer` | secp256k1 sighash (`0x9bd7e06f…`), args twenty zero bytes |
| v2 (`data1`) | `0x3e27a1a2…a282:0` | 52,344 | no (`0000000000000000`) | `invalid_trailer` | code hash `0x00…00`, `data`, args `0x` |

Sources: `results/binding-check.json`, `results/cli-inspect.txt`, `results/harness-output.jsonl`.

- **None of the three carries a Binding Trailer 1.** CKB IDL's client flow says: "Do not trust an IDL merely because it parses. Verify its exact bytes against the deployed bound code data before using it to encode or sign a witness" (`idl-client-flow.md`). So, by CKB IDL's own rules, no IDL for these locks can be verified today.
- **None can get one without changing the script's identity or its owners acting:**
  - **v2 uses `data1`,** so its code hash is the code cell's data hash. `ckb-idl bind` on the v2 binary gives bound data with hash `0x299e691a…bce1`, not the v2 code hash `0x36c971b8…0d29`. A bound v2 would be a new script with new addresses, which C1 rules out.
  - **The genesis and v2 code cells are locked by a script whose code hash is all zeros,** which no cell's data can hash to (RFC 0022's code-hash rule).
  - **The 2024 code cell is locked by the sighash lock with all-zero args.** docs.nervos.org uses the same convention for xUDT: "This Script is not upgradeable due to zero lock (lock args with all zeros)" (`website/docs/ecosystem-scripts/11-xudt.mdx` L330 at 6a6152f).
  - So none of the three code cells can be replaced by a bound one.
- **CKB IDL's own plan for this case:**
  - the ROADMAP defers "Manual-IDL authoring and attestation tooling for legacy scripts";
  - the registry's milestone M2 (weeks 4-7) plans "interface binding checks and legacy attestations".
  - The registry is testnet-first, and "Mainnet operation" is outside its initial scope (`script-registry` `docs/RELEASE_PLAN.md` at b37ef14).
  - All three multisig deployments hold mainnet funds ([background §3](../../background.md#3-the-three-multisig-deployments)).

## 3. What reuse would cost, against defining the layout in Sigsheet

| | Reuse CKB IDL for the multisig witness | Define it in Sigsheet (point to the lock's own layout) |
|---|---|---|
| **Bytes per file** | 18,372 bytes to carry the N ≤ 5 union document, 591 to 683 bytes for one configuration, or 32 bytes for a digest that a reader must resolve somewhere | 0 extra. The layout follows from the lock and the multisig config, which every path carries anyway: 64 bytes for 2-of-3 and 104 for 3-of-5, the `4 + 20N` script part |
| **Code a wallet adds** | An IDL 0.1.0 client. In Rust: `ckb-idl-client`, 1,692 lines before its test modules (1,318 code lines), with `reqwest` and `tokio`. In TypeScript (Neuron, CCC): no published client, since npm has no CKB IDL package under any of the 7 names tried, and `npm search ckb-idl` finds none | **None.** All three already build and parse this layout: ckb-sdk 5.0.0 (used by ckb-cli) has `MultisigConfig`, 125 lines (`signer.rs` L142-L266); CCC 1.23.1 has `MultisigCkbWitness`, 260 lines (`signerMultisigCkbReadonly.ts` L50-L63, L69-L141, L142-L314); Neuron has `Multisig.serialize`, 6 lines (`models/multisig.ts` L20-L25), plus its signing code |
| **Trust** | Not verifiable for any existing deployment (section 2) | The layout is the lock's own rule. The config is checked by hashing it against the lock args ([background §1](../../background.md#1-the-multisig-lock)) |
| **Adoption** | Every wallet takes a new dependency on a pre-release toolchain: the client README says "This project is pre-release". crates.io had 73 downloads of `ckb-idl-client` on 2026-11-18. TypeScript support is planned for milestone M4 (weeks 12-15) | Nothing new for the layout itself |
| **Duplication risk under C4** | None for the layout, since CKB IDL has no description of this lock. Writing one now would make a legacy-script IDL ahead of CKB IDL's own planned attestation work (ROADMAP; registry M2), and so would compete with it | Low, as long as Sigsheet points to the lock's layout and doesn't define a general witness-description language |

Sources: `results/loc.json`, `results/idl-sizes.txt`; the client README ([ckb-idl-client at e7d8124](https://github.com/ckb-idl/ckb-idl-client/blob/e7d8124921dc640018004a4a031fc6146535e334/README.md)); package lookups in `README.md` step 7.

## Answer

1. **CKB IDL 0.1.0 can't describe the multisig witness in general.** It can describe one configuration per document, or every configuration up to N = 5 through a union-tag workaround, in an 18,372-byte document.
2. **No IDL for the three deployed multisig locks can be verified under CKB IDL's commitment rules,** and none of their code cells can ever be bound. CKB IDL's own plan for such scripts ("legacy attestations", registry M2) is future and testnet-first.
3. **Defining the layout in Sigsheet, by pointing to the lock, is cheaper on every measure here:**
   - it adds 0 bytes per file and 0 lines of new wallet code, since all three wallets already have this codec;
   - reuse would add an 18,372-byte document, or a digest to resolve, and an IDL client: 1,318 Rust code lines, and no TypeScript client exists.

   That supports the working framing: Sigsheet carries the partly signed transaction, and CKB IDL describes witnesses of scripts that publish an IDL.
4. **It doesn't settle the overlap with CKB IDL's deferred "signing and partial-signing metadata",** because CKB IDL's text doesn't define what that will hold. The only trace in the code is the client's `SigningInfo` ("Legacy signing metadata container", with `algorithm`, `message` and `hasher`). That struct describes a script's signing rule, not the partial signatures of one transaction ([`ckb-idl-client` `src/types.rs` L45-L56](https://github.com/ckb-idl/ckb-idl-client/blob/e7d8124921dc640018004a4a031fc6146535e334/src/types.rs#L45-L56)). This stays open ([design record §6.2](../../design-record.md#62-ckb-idl-complements-ckb-idl-instead-of-duplicating-it-c4)).
