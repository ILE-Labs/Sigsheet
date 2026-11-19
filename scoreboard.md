# Scoreboard

The design paths that pass every gate ([design record §1.2](design-record.md#12-the-goal)), scored on the design-stage measurements. Each criterion is scored 0-5; a criterion's points are its weight × score / 5; formats are scored out of 100, ways of gathering out of 75. A score marked **provisional** wasn't measured; the cell says what would measure it. No open claim decides a score.

The paths are described in [paths.md](paths.md). D is merged into C, and G is dropped (it fails C1 and C3). **B is scored with the witness templates added ("B+w"):** B as designed carries no witnesses, so it fails X2's case S9 (G1: its readers compute the wrong message) and its round trip onto the building-packet profile (C4); with one added field it passes every case ([X2](experiments/X2/results.md#1-round-trips)).

## Formats (G1): A, B+w and C

| Criterion (weight) | A: building-packet profile | B+w: PSBT-style, per input, with witness templates | C: JSON per lock group (with D) |
|---|---|---|---|
| Security (25), **measured** ([X4](experiments/X4/results.md)) | **3**: every attack is caught by a profile-aware reader, but a CoBuild reader that doesn't know the profile trusts `resolved_inputs` and would show a 1,000,000 CKB fee lie ([X4](experiments/X4/results.md#2-each-attack-in-each-format)) | **4**: every attack caught by the same four checks as C; its network id is unsigned and protects nothing | **4**: every attack caught: previous transactions by hash, config by hash, signatures by the lock's message, a deterministic merge; no display fields. The lock accepts high-s twins on chain, which the merge normalizes |
| Adoption cost in each wallet (20) | **2**, **measured**: +103 lines (95 code) on top of C even in CCC, which has a Molecule library and a `BuildingPacket` codec in `@ckb-ccc/spore`; ckb-cli and Neuron have no CoBuild code (the Rust types are 5,200 generated lines in cryptape's proof of concept) ([X6](experiments/X6/results.md#4-what-path-a-adds-on-top-of-c-measured-in-ccc-and-how-b-compares)) | **3**, **provisional**: not patched in a wallet. Its format layer in the prototypes is 98 code lines plus 77 of Molecule decoding, against C's 63 ([X6](experiments/X6/results.md)). A wallet patch would measure it | **4**, **measured**: ckb-cli +381 code lines, CCC +229, Neuron +137, each through the wallet's own signer; every wallet's own tests unchanged ([X6](experiments/X6/results.md#1-path-c-in-each-wallet-the-patch-its-hook-points-its-size)) |
| Fit with CoBuild and CKB IDL (15) | **5**: it *is* the building-packet profile; no signing-rule field ([X2](experiments/X2/results.md#4-the-ckb-idl-boundary-what-a-signers-message-computation-reads)) | **4**: maps onto the profile through the same model as C (B as designed doesn't); no signing-rule field | **4**, **measured**: C → A → C and A → C → A byte-identical on 12 of 12 cases ([X2](experiments/X2/results.md#3-c4-c-maps-losslessly-onto-the-building-packet-profile)); a CoBuild tool needs a mapping layer (95 code lines in CCC); no signing-rule field; reusing CKB IDL would add code, not remove it ([X6](experiments/X6/results.md#5-the-ckb-idl-reuse-alternative-where-it-can-be-measured)) |
| Offline completeness (10), **measured** ([X2](experiments/X2/results.md)) | **5**: every message computed from the file alone in 12 of 12 cases | **5**: the same, with the witness templates (11 of 12 without them) | **5**: 12 of 12 ([X2](experiments/X2/results.md#1-round-trips)) |
| Simplicity (10), **measured** | **2**: format layer 199 code lines plus Molecule decoding (77), several profile rules, two encodings | **3**: format layer 98 plus Molecule decoding (77); per-input maps that repeat shared previous transactions (PR #34: 1.3 MB against C's 733 KB) | **5**: format layer 63 code lines; one merge rule, one finalize rule ([X6](experiments/X6/results.md), [X2](experiments/X2/results.md#2-bytes-zlib-level-9-in-brackets)) |
| Extensibility (10), not tested | **4**: a new lock kind is a new action keyed by its script hash | **4**: readers pass unknown keys through | **4**: the lock kind comes from the input cell; a reader can refuse an unknown group and still pass the file on ([X5](experiments/X5/results.md) F7 shows a tool passing a file it can't sign) |
| Phase 1 fit (10) | **2**, **measured**: the profile, a Molecule codec and a JSON view; the CoBuild types are missing in two of the three wallets | **3**, **provisional**: not patched | **4**, **measured**: the code each wallet needs is 137-381 code lines, with each wallet's tests unchanged |
| **Total (of 100)** | **64** | **74** | **84** |

Points: A = 15 + 8 + 15 + 10 + 4 + 8 + 4; B+w = 20 + 12 + 12 + 10 + 6 + 8 + 6; C = 20 + 16 + 12 + 10 + 10 + 8 + 8.

## Ways of gathering (G2), on top of a format

Scored on the criteria where they change something (out of 75). The in-format mechanism was tested end to end; E and F weren't prototyped, so their scores stay provisional.

| Criterion (weight) | In-format: files passed along, or posted and merged by anyone | E: optional relay transport | F: signature cells on chain |
|---|---|---|---|
| Security (25) | **4**, **measured**: nothing new to trust; every file is checked the same way; merges by three different tools give the same bytes ([X5](experiments/X5/results.md) F2) | **3**, provisional | **2**, provisional |
| Adoption cost (20) | **5**, **measured**: nothing beyond the format patches ([X5](experiments/X5/results.md)) | **2**, provisional | **1**, provisional |
| Offline completeness (10) | **5** | **5** | **3** |
| Simplicity (10) | **5** | **2** | **1** |
| Phase 1 fit (10) | **5**, **measured**: seven flows committed with the format patches alone | **2**, provisional | **1**, provisional |
| **Total (of 75)** | **70** | **41** | **24** |

One more input for E: a signer's own contribution can be posted as 367 bytes (one signature with the ids that place it), below every relay limit seen, while a whole PR #34 file exceeds them all ([X7](experiments/X7/results.md#3-limits)).

## What this says

- **C is first (84), then B+w (74), then A (64).** B needs a witness field it doesn't have, and its per-input layout costs 77% more bytes on PR #34.
- **C meets C4** by the measured lossless mapping onto the building-packet profile; the CKB IDL framing holds and is efficient on the measurements ([design record §6](design-record.md#6-fit-with-cobuild-and-ckb-idl)).
- **Still provisional:** B's adoption and phase 1 fit (no wallet patch), extensibility for all three (not tested), and E's and F's scores. B+w would pass C only if both of its provisional scores were 5, above C's measured 4.
- **The rules added after the attacks considered** (a merge refusal, a config check, a single-key args check, token display, inclusion proofs for Nervos DAO withdrawals) are small and were tested on the prototypes only; their cost in the wallets isn't measured. The same rules would apply to any format that carries proofs (B+w, A), so they don't change the order.
