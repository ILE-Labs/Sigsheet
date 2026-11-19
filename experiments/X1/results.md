# X1 results: the signing message across tools

Conditions (design-stage): 2026-11-18 (UTC); local devnet (ckb 0.210.0) and mainnet data read from `https://mainnet.ckb.dev/`; ckb-cli 2.0.0 (80efc21), ckb-sdk 5.0.0, `@ckb-ccc/core` 1.23.1, Neuron v0.204.1 (d3a7467); fresh test keys. Full table: `results/message-table.md` (generated). Raw output: `results/`.

## Answer

**Yes, with one exception.** On all 12 cases (2 real, 10 synthetic; 15 lock groups), the message from the independent implementation (M) equals, byte for byte, the message from:
- CCC (`Transaction.getSignHashInfo` / `SignerMultisigCkbReadonly.getSignInfo`): 15 of 15;
- ckb-cli 2.0.0's own `build_signature`: 15 of 15;
- ckb-sdk 5.0.0's `ScriptSigner::sign_tx`: 15 of 15 (for R2 it computed the same message, then refused to add a signature to a witness that already held M);
- Neuron v0.204.1's `signSingleMultiSignScript`, run in Node: 12 of 13 multisig groups (Neuron has no code for the two single-key groups in this path). **The exception is S9**, a transaction with a witness beyond its inputs: Neuron's message leaves that witness out (`0xd8d69dfc…` instead of `0xa63aaae8…`).

The lock script is the judge: every synthetic case was committed on devnet with signatures that each tool made, and both negative controls were rejected.

## Real signatures

| Case | Signatures | Result with message M |
|---|---|---|
| R1 fiber-scripts PR #34, multisig `0x66712ae3…` (3-of-5, v2) | 1 in `mainnet.json` + 4 pasted in PR comments | All 5 recover to members: file = member 1 (`0x5cf02830…`), comment-1 = member 2, comment-2 = member 4, comment-3 = member 0, comment-4 = member 3. Five distinct members signed for a threshold of 3 |
| R1, single-key input `0x5cf02830…` | 1 in `mainnet.json` | Recovers to `0x5cf02830…` |
| R1 as committed on mainnet (tx `0x4396de69…92ee`, block 20,965,430, 2026-11-09 03:16:08 UTC) | 3 in the witness | Members 3, 1, 2: comment-4's, the file's, comment-1's |
| R2, the genesis 2-of-3 payment (tx `0x63a7f3a5…baa4`, block 20,354,743) | 2 in the witness | Members 0 and 1 of the 2-of-3; the multisig script hashes to the lock args `0x31a2b249…4f` |

## Devnet transactions (all committed)

| Case | Signatures used, by tool | Tx hash | Block |
|---|---|---|---|
| S1 genesis 2-of-3 | k1 and k2 added to ckb-cli's `tx` file with `tx add-signature` from Neuron's and CCC's output; **finalized and sent by `ckb-cli tx send`** | `0xee7aabc3…9405` | 1122 |
| S2 2024 deployment | k1 CCC, k3 Python (ckb-cli and Neuron can't sign this lock) | `0x2d8b5331…9ba7` | 1126 |
| S3 v2, two inputs | k2 Neuron, k3 ckb-cli | `0xc72eeeb7…7c18` | 1130 |
| S4 v2, R=1 | k4 (required) CCC, k2 ckb-cli | `0x6c360671…cb53` | 1134 |
| S5 v2, since in args | k1 ckb-cli, k3 CCC | `0x89375fd7…f6bd` | 1138 |
| S6 two multisig groups | genesis: k1 Neuron, k2 ckb-cli; v2 3-of-5: k1 CCC, k3 ckb-cli, k5 Neuron | `0xc5df611a…7a18` | 1226 |
| S7 multisig + single key | multisig: k1 CCC, k2 Neuron; single key k7: ckb-cli | `0x5dc1d6ad…d625` | 1230 |
| S8 Neuron export | k1 from Neuron's exported file, k3 ckb-cli | `0xaaeb866b…d77e` | 1234 |
| S9 extra witness | k2 ckb-cli, k3 CCC | `0x7ecdcb5b…57d6` | 1238 |

Full hashes are in `results/assembly.json` and the committed transactions in `data/devnet/committed/`.

**ckb-cli, CCC and Neuron produce byte-identical signatures** for the same key and message in every case (`results/verify.json`): all three sign deterministically (RFC 6979). So the "by tool" column says which tool produced the bytes used, but the bytes would be the same from any of the three. Identical signature bytes from three separate code paths confirm, independently of M, that they sign the same message.

**Negative controls** (`test_tx_pool_accept`, so nothing was committed):
- S4N (R=1): signatures from members k1 and k2, without the required k4: rejected, `ValidationFailure ... error code -52` (ERROR_VERIFICATION).
- S9 with Neuron's k2 signature and CCC's k3 signature on the full transaction: rejected, error code -52.
- S9 as Neuron itself finalizes it (both signatures by Neuron, the witness beyond the inputs dropped): accepted in the dry run. Neuron's transaction is valid on its own; it just can't be merged with signatures made over the full transaction.

## Interoperability findings

1. **Witnesses beyond the inputs.** The lock hashes every witness whose index is at or beyond the number of inputs ([secp256k1_blake160_multisig_all.c L259-L278](https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c#L259-L278)). ckb-cli, ckb-sdk and CCC do too. Neuron's `signSingleMultiSignScript` doesn't, and `signMultisig` drops those witnesses from the signed transaction (transaction-sender.ts L443). So a file whose transaction carries such a witness gets signatures from Neuron that fail next to signatures from the other tools (S9). A shared format must say whether these witnesses are part of what is signed and must keep them.
2. **Deployments.** ckb-cli refuses the 2024 deployment (`Input(no.1) invalid lock script code_hash: 0x6283a479…`); Neuron's config code throws `Unknown Multisig Code Hash`. CCC signs all three. Neuron's multisig config has no `since`, so it doesn't recognise a multisig lock whose args carry one (S5); its message function still gives the right message.
3. **Four ways to hold partial signatures, none of them shared:**
   - ckb-cli `tx` file: outside the transaction, `signatures` keyed by lock args;
   - Neuron: appended after the multisig script, so the lock grows by 65 bytes per signature (129 bytes after one signature of a 2-of-3), plus `transaction.signatures` keyed by lock hash, listing signer key hashes;
   - CCC: the lock at its final length, M slots, unused slots zero-filled (194 bytes after one signature of a 2-of-3);
   - ckb-sdk: requires the final length and fills empty slots; refuses a lock that already holds M signatures.
4. **Reading each other's files.**
   - Neuron's ckb-cli importer (`parseMultisigTxJsonFromCkbCli`) drops ckb-cli's signatures: after importing ckb-cli's S1 file holding two signatures, `signatures` is `{}`. For a v2 file it gives the inputs the genesis lock, and Neuron then can't sign (it shows the "unrecognised lock" dialog and adds nothing). Run with Neuron's own code: `results/neuron-ckbcli-import.json`.
   - CCC's `Transaction.from` accepts Neuron's exported transaction without an error and computes the right hash, but turns Neuron's witness object into `0x`: the partial signature is lost silently (`results/s8-ccc-reads-neuron.json`).
   - ckb-cli has no reader for Neuron's file.
   - CCC's `Transaction.from` throws on the `transaction` object of a ckb-cli `tx` file (snake_case RPC JSON): `TypeError: undefined is not iterable`. CCC reads it only through `JsonRpcTransformers.transactionTo` from `@ckb-ccc/core/advanced`, which X1's harness used (`results/ccc-reads-ckbcli-json.json`, `ccc/ckbcli-json-from.mjs`).
5. **Offline verification is possible when the file carries the input transactions.** From Neuron's export alone, the independent implementation checked that each `context` transaction hashes to its input's out point, so the input cells are genuine; then it recomputed the transaction hash and the message and recovered the partial signer (`results/s8-neuron-export.json`). The same holds for ckb-cli's deploy file with `used_input_txs` (R1). A ckb-cli `tx` file or a bare CCC transaction doesn't carry input cells; CCC needs a client (here, a filled cache) to find which inputs belong to which lock.
6. **The PR #34 deploy file's `multisig_config.lock_code_hash` is the genesis code hash, while its lock is v2.** ckb-cli fills that field with the genesis code hash when it's missing, "for compatibility" (tx.rs L849-L859), and the message doesn't depend on it. So the field can't be trusted to name the deployment; the input cell's lock can.
7. **Neuron asks the user about every lock group it has no multisig config for**, on every signing (S6: 2 then 3 dialogs; S7: one per signer for the single-key input). This is in Neuron's `signMultisig` (L364-L381).

## Side check: more than M signatures in ckb-cli

On case S4N's still-unspent cell (R=1, M=2, N=3), through ckb-cli's own `tx` file: with three signatures (k4, k1, k2), `ckb-cli tx send` refused: "Invalid multisig signature length for lock_arg: 0x3fb8b1b4263c8afbb694bf1a870bd88bfdbe6060, got: 3, expected: 2". With exactly the required k4 and k2 it sent the transaction, committed in block 2978 (`results/ckbcli-threshold-check.json`, `scripts/ckbcli_threshold_check.py`). So whoever finalizes for ckb-cli must drop extra signatures first, as on PR #34 (5 signatures for a threshold of 3).

## Numbers

- Messages compared: 15 lock groups × 5 implementations (M, CCC, ckb-cli, ckb-sdk, Neuron).
- Signatures checked against M: 92 (`results/verify.json`); 90 valid; the 2 invalid are Neuron's S9 signatures, as expected.
- Devnet: 9 transactions committed (blocks 1122-1238), 2 negative controls rejected, 1 dry run accepted.
- **The fiber-scripts PR #34 deploy file** (`data/fiber-scripts-34/mainnet.json`, 904,588 bytes, SHA-256 `8563ba8dcd0d051822dd0cc21db995dc8e6a2984e900d3500068f0185a07b51e`, the file at fiber-scripts `026027f`; measured 2026-11-18 by `scripts/measure_pr34.py`, which finds each field's byte span in the file as stored, without re-serializing; `results/pr34-size.json`):
  - `used_input_txs` (the input transactions the file carries): 735,190 bytes, **81.27% of the file**. It holds two transactions: `0x95006eee…`, 570,410 bytes, which `cell_tx` spends (both its inputs), so **63.06% of the file proves `cell_tx`'s input cells**; and `0x4396de69…`, 164,624 bytes, which is `cell_tx` itself, kept for the dep-group step. Their outputs data is 283,056 and 80,936 bytes once decoded from hex: contract binaries.
  - `cell_tx`: 164,490 bytes (18.18%); everything else: under 5 KB.
