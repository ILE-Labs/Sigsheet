# X2: does each format round-trip every case? (and the CoBuild mapping and the CKB IDL boundary)

**Questions:**
1. Can each candidate format (C; B, with its per-input layout; A, the building-packet profile) encode every case, decode it, recompute the signing message from the file alone, verify the signatures and finalize a valid transaction? What does each take, in bytes?
2. **C4:** does C map losslessly onto the building-packet profile and back, byte for byte, with the messages and signatures surviving? A format that fails can't claim to build on CoBuild.
3. **The CKB IDL boundary:** which fields of the file does a signer's message computation read? The design rule (no Sigsheet field describes a signing rule) holds only if they are the transaction, the previous transactions, the multisig config, and the lock's code hash and hash type.

## Method

- **Prototypes** ([`../prototypes/`](../prototypes/README.md), Python standard library on X1's independent `ckbcore.py`): one shared core (resolving inputs from the carried previous transactions, lock groups, the lock's message rule, verification, the merge and finalize rules, the lock's rules run in Python) and one codec per format: `fmt_c.py`, `fmt_b.py` (B as designed, and "B+w" with the witness templates added), `fmt_a.py` (Molecule, every profile rule checked on decoding, plus A's 1:1 JSON view).
- **Cases** (`cases/*.json`, written by `../prototypes/cases.py` from each case's own files):
  - R1, fiber-scripts PR #34, **replayed from the real deploy file**: `cell_tx`, `used_input_txs`, `deployment.multisig_config` (members from its addresses; its wrong `lock_code_hash` ignored), `cell_tx_signatures`, and the four PR comments as pasted. Six signatures: five members of the 3-of-5 and the single-key input.
  - R2, the genesis 2-of-3 payment: the committed mainnet transaction, its previous transaction, the two signatures in its witness.
  - S1-S9 and S4N: X1's devnet cases, their funding transaction, and the signatures from the committed transactions (S4N: the two non-required members' signatures from X1's ckb-cli file, so it stays unready).
  - Every model reproduces X1's message for every group (`cases.py` checks it).
  - R1 and R2 are mainnet inputs, not in this branch ([mainnet-inputs.md](../mainnet-inputs.md)).
- **Steps per case and format** (`scripts/x2.py`): encode; size (and zlib level 9); strict decode, compare with the model; re-encode, compare bytes (canonical form); compute every group's message from the encoded file through the format's own field names, recording every field read (`../prototypes/record.py`); verify every signature with those messages; finalize with the finalize rule (D12) and run the lock's rules on the result; check the transaction hash.
- **C4 mapping:** C → A → C and A → C → A, compared byte for byte; messages and signatures compared on both sides.
- **Boundary:** the recorded field paths, collapsed (`[]` for indices, `{}` for hash keys) and classified (`classify` in `scripts/x2.py`); any path outside the transaction, the previous transactions and the multisig config would be "OTHER".

## Exact commands

From `experiments/`:

```sh
(cd prototypes && python3 -I -X utf8 cases.py)          # writes X2/cases/*.json; S4N's previous transaction is
                                                        # cached in X2/data/ (it came from the devnet RPC once)
(cd X2 && python3 -I -X utf8 scripts/x2.py > results/x2.json)
```

`./bench/run.sh` re-runs `x2.py` offline and compares every size, round trip and boundary result with `results/x2.json` (benchmark `x2`).

## Environment

2026-11-18 (UTC); Python 3.14.4; X1's `ckbcore.py`; X1's mainnet data (fetched from `https://mainnet.ckb.dev/` on 2026-11-18) and the fiber-scripts deploy file (SHA-256 `8563ba8d…b51e`, checked by X1); the local devnet (ckb 0.210.0) for S4N's funding transaction only. CoBuild schemas: ckb-transaction-cobuild-poc `e29514f` (`schemas/basic.mol`); the MultisigAction schema from ckb-multisig-cobuild-poc `84bdc99` (`src/lib/multisig-lock-action.js`), plus A's `input_transactions`.

## Files

- `cases/`: the case models; `data/`: the cached devnet transaction.
- `scripts/x2.py`; `results/x2.json` (every number in the results, the field paths, per-case details).
- `results.md`: the answers.
