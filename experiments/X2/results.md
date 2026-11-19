# X2 results: round trips, the C4 mapping and the CKB IDL boundary

Conditions (design-stage): 2026-11-18 (UTC); the prototypes in `../prototypes/` on X1's implementation; 12 cases (R1 replayed from the real PR #34 deploy file and comments, R2 from mainnet, ten X1 devnet cases). Raw output: `results/x2.json`. Commands: `README.md`.

## 1. Round trips

| Format | Lossless (model in = model out) | Canonical (re-encode = same bytes) | Messages from the file alone = X1's | Signatures verified | Finalized, lock rules pass |
|---|---|---|---|---|---|
| **C** (JSON, per lock group) | 12 of 12 | 12 of 12 | 12 of 12 | 32 of 32 | 11 of 11 ready cases |
| **B as revised** (per input, no witnesses) | **11 of 12** | 12 of 12 | **11 of 12** | **30 of 32** | 10 of 11 |
| **B+w** (B plus the witness templates) | 12 of 12 | 12 of 12 | 12 of 12 | 32 of 32 | 11 of 11 |
| **A** (building-packet profile, Molecule) | 12 of 12 | 12 of 12 | 12 of 12 | 32 of 32 | 11 of 11 |

S4N is the twelfth case: its required member didn't sign, so every format refuses to finalize it, as it must.

- **B as designed fails S9**, the transaction with a witness beyond its inputs. B's field table carries the raw transaction and per-input data but no witnesses, so a B reader must assume one empty witness per input. S9's extra witness is lost, the message differs from the lock's, and neither real signature verifies (0 of 2). That is the same failure X1 found in Neuron ([background §7](../../background.md#7-the-signing-message-across-tools)). B needs the witness templates; "B+w" adds them as one global field and then passes every case.
- **C and A pass every case,** including R1 replayed from the real deploy file: its five member signatures and the single-key signature all verify, and the finalized transaction (3 of the 5 member signatures, chosen by the finalize rule, D12) passes the lock's rules and has the committed transaction's hash, `0x4396de69…92ee`.

## 2. Bytes (zlib level 9 in brackets)

| Case | C | B | B+w | A (Molecule) | A's JSON view |
|---|---:|---:|---:|---:|---:|
| R1 fiber-scripts PR #34 | 733,078 (247,785) | **1,300,648** (445,344) | 1,300,721 (445,366) | **367,378** (222,827) | 734,217 (248,461) |
| R2 genesis 2-of-3 payment | 2,371 (914) | 2,221 (865) | 2,278 (883) | 2,037 (1,136) | 3,458 (1,456) |
| S3 two inputs, one group | 4,788 (1,133) | 8,067 (1,211) | 8,140 (1,227) | 3,405 (1,396) | 6,205 (1,744) |
| S6 two multisig groups | 6,065 (1,506) | 9,010 (1,548) | 9,083 (1,567) | 4,786 (1,840) | 8,351 (2,243) |
| S7 multisig + single key | 5,377 (1,276) | 8,407 (1,324) | 8,480 (1,344) | 3,636 (1,513) | 6,712 (1,860) |
| S1 genesis 2-of-3 (S2, S4, S5, S8 and S9 are within 60 bytes of it in every format) | 4,653 (1,132) | 4,635 (1,154) | 4,692 (1,172) | 3,244 (1,389) | 5,862 (1,727) |

- **B's per-input layout repeats a previous transaction for every input that spends from it.** Both of PR #34's inputs spend outputs of one 284,008-byte transaction, so B carries it twice: 1,300,648 bytes, 77% more than C. The same happens in S3, S6 and S7, whose inputs share a funding transaction. C and A carry each previous transaction once.
- **A is about half of C uncompressed** (binary against hex), as X2a measured. Compressed, the gap shrinks to 10% for PR #34 (222,827 against 247,785), and A is *larger* than C for every small case (its fixed parts, such as the `ScriptInfo` schema text, don't compress away).
- **A's own JSON view is larger than C** (734,217 against 733,078 for PR #34; 3,458 against 2,371 for the genesis 2-of-3 payment): it carries C's content plus CoBuild's fixed parts.

## 3. C4: C maps losslessly onto the building-packet profile

| Check | Result |
|---|---|
| C → A → C, byte for byte | **12 of 12** identical |
| A → C → A, byte for byte | **12 of 12** identical |
| The messages computed from each side | equal in 12 of 12 |
| The signatures read from each side | equal in 12 of 12 |

So C passes the round trip C4 requires, on every case, and C4 is met for C. B+w carries the same model, so it maps through C; B as designed doesn't (it loses S9's witness), so B as designed fails C4 on S9. The mapping works because both formats hold the same five things (the transaction with witness templates, the previous transactions, the multisig configs, the signatures, and nothing else); the profile's other parts are fixed or derived (`message` empty, `change_output` none, `resolved_inputs` equal to the previous transactions' outputs with empty data, `script_infos` derived from the deployments).

## 4. The CKB IDL boundary: what a signer's message computation reads

| Format | Fields read (collapsed) | Outside the transaction, the previous transactions and the multisig config |
|---|---|---|
| C | `transaction.*` (every raw field and the witnesses); `context{}.*` (every field of each previous transaction, to hash it; then `outputs[].lock.code_hash`, `hash_type`, `args`); `multisig_configs{}.require_first_n`, `threshold`, `public_key_hashes` | **none** |
| A | `payload.*`; `lock_actions[].data.input_transactions[].*` (with `outputs[].lock.code_hash`, `hash_type`, `args`); `lock_actions[].data.config.*` | **none**: not `message`, `script_infos`, `script_info_hash`, `script_hash`, `resolved_inputs` or `change_output` |
| B, B+w | `SIGSHEET_GLOBAL_RAW_TX`, `SIGSHEET_GLOBAL_WITNESSES` (B+w), `SIGSHEET_IN_PREVIOUS_TX`, `SIGSHEET_IN_MULTISIG_CONFIG` | **none**: not `NETWORK_ID`, `SINCE_REQUIREMENT` or `PARTIAL_SIG` |

Full path lists: `results/x2.json`, key `boundary`.

**The boundary rule holds on the measurement:** in every format and every case, the message computation reads only the transaction, the previous transactions (from which it takes each spent output's lock: code hash and hash type to pick the rule, args to find the config and the since) and the multisig config. No field describes a signing rule, and none is read. The rule itself is code in `core.group_message`, the lock's own message rule ([background §1](../../background.md#1-the-multisig-lock)), selected by the code hash and hash type.

## Answer

1. C and A round-trip every case, real and synthetic; so does B once it carries the witness templates. B as revised fails the extra-witness case (S9) and duplicates shared previous transactions (1.3 MB for PR #34).
2. C maps onto the building-packet profile and back byte for byte on all 12 cases: C4 is met for C.
3. The IDL boundary holds: a signer reads the transaction, the previous transactions and the multisig config, and nothing else.
