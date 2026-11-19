# XRT results: attacks and objections, first round, measured

Conditions (design-stage): 2026-11-19 (UTC); local devnet (ckb 0.210.0; the genesis multisig binary byte-identical to mainnet's, the 2024 and v2 binaries copied from mainnet); fresh test keys; the design-stage prototypes unchanged. Commands: `README.md`. Raw output: `results/`. How the design answers each: [design record §5](../../design-record.md#5-security-analysis).

## XRT-1. Which valid signature sets each deployed binary accepts

| Run | Deployment | Sets accepted | Rejected sets |
|---|---|---|---|
| 1 and 2 (N = 2 to 12, every M; ~15 random sets per configuration; member and descending order) | genesis, R = 0 | **1,047 of 1,297** | 250, all in N = 11 or 12 |
| | genesis, R = 1 | 19 of 21 | 2 (N = 12) |
| | 2024 | **472 of 472** | 0 |
| | v2 | **460 of 460** | 0 |
| 3 (N = 13, 16, 20, 24; M from 1 to 16; one varying position) | genesis, member order | **397 of 423** | 26: position 10 when M ≤ 10; position 18 when M = 1 |
| | genesis, descending order | 330 of 388 | 58: also positions 20-23 (N = 24) |
| | v2 (N = 24) | 76 of 76 | 0 |

Sources: `results/genesis-sweep.json` (run 2, funding `0xa4bdf46c…cf3b`), `results/genesis-sweep-run1.log` (run 1, the same counts per configuration), `results/genesis-positions.json` (run 3, funding `0xe8f34651…0a3f`). Every rejection is "TransactionFailedToVerify" on `Inputs[0].Lock`.

- **The rule, in member order (the order Sigsheet's finalize writes):** in runs 1 and 2, a set is rejected exactly when the member at **position 10** (the 11th member) signs and M ≤ 10: 1,318 of 1,318 genesis sets fit. Run 3 adds **position 18 when M = 1** (N = 20 and 24). No set within the first M positions was ever rejected. The two runs on different cells and transactions gave the same counts, so the outcome doesn't depend on the transaction's data.
- **Descending order rejects more** (positions 20-23 for N = 24 with M ≥ 2), so the order matters on the genesis binary; member order (ascending positions) is the one the design's finalize writes.
- **The 2024 and v2 binaries accept every set**, as the 2024 fix (`used_signatures` sized by N, [background §3](../../background.md#3-the-three-multisig-deployments)) predicts.
- **The objection's rule (a member at position ≥ M is rejected) is wrong as stated:** a member at position ≥ M is fine except at those positions (X5 F3, a 2-of-3 signed by members 1 and 2, committed in block 17,348). The defect is real for larger multisigs: in member order, a genesis multisig with N ≥ 11 and M ≤ 10 can't use its 11th member's signature.
- **A repeated key:** a 2-of-3 whose script lists one key twice is spent by that one key's signature and its high-s twin, on both genesis and v2 (`repeated_key_2_of_3`: accepted). So such an address is controlled by one key.

## XRT-2. Prototype checks (no chain)

| Check | Today's prototype | Candidate rule |
|---|---|---|
| Unused entries: a context entry or config no input uses | the reader refuses the file ("1 previous transaction(s) not spent by any input"; "a multisig config that no input uses"); an unvalidated merge carries the entry into a result the reader then refuses | merge only files the reader accepts, keeping the entries the transaction uses: the merged file is accepted |
| Junk signatures: 20,000 junk entries (valid-looking r and s, each needing a key recovery) in a 3.6 MB file | **106.49 s** to read (pure-Python secp256k1: recover, then check membership) | check that the filed signer is a member before recovering: **0.022 s**, 2 recoveries |
| Canonical check first: a canonical file with a valid signature by a non-member | read; the signature is dropped with a warning (the canonical check runs on the parsed file) | no change: a wording fix |
| Template with an extra field: a first-witness template that is a `WitnessArgs` with a fourth field (and an `input_type`) | **accepted**; the message equals that of the same template without the fourth field (the prototype rebuilds the canonical form) | refuse a template unless it re-encodes to itself (exactly three fields) or is `0x` |
| Duplicate out point: a transaction listing one out point twice | **accepted**; the fee shown is 1,000.001 CKB (the input counted twice); the chain would reject it | refuse duplicate out points |

Source: `results/prototype-checks.json`. A Nervos DAO withdrawal's fee is measured on the devnet in [XRTb-3](../XRTb/results.md#xrtb-3-a-nervos-dao-withdrawal-of-two-deposits).

## XRT-3. A lock the reader doesn't sign

A v2 2-of-3 input next to an input under a lock the "v1 reader" doesn't sign (the single-key lock, treated as unknown by patching the prototype; the "v0.2 reader" is the prototype as it is). Funding `0x585f4997…5103`.

| Part | Result |
|---|---|
| A. The v1 reader with both groups | can't finalize the whole file ("has a lock kind Sigsheet v1 doesn't sign"), as designed |
| A. Candidate rule: finalize the groups it signs, leave the other group's witness as in the template; the other lock's own signer then signs the final transaction | **committed**: `0x0942c9cf…8984`, block 50,247. The multisig signatures survive the later witness, as the lock's message predicts ([background §1](../../background.md#1-the-multisig-lock)) |
| B. The v0.2 reader signs the other group into the file; the v1 reader merges its own signatures | today's v1 merge **drops** the other group's signature; the candidate rule (keep it, unverified and unchanged) **keeps** it |
| B. The v0.2 reader finalizes the file the candidate rule produced | **committed**: `0xe887f919…92f2`, block 50,251 |
| C. A genesis 2-of-3 with 20-byte args, its input's since set to `0x8000000000000001` (a relative flag) | the prototype gives **no warning**; the lock **rejects** it (dry run); with since 0 it is accepted |

Source: `results/unknown-groups.json`.

## XRT-4. Creating the file inside the wallets

| Flow | Steps | Result |
|---|---|---|
| C1 | ckb-cli's own `tx init`, `add-multisig-config`, `add-input`, `add-output` build the transaction; ckb-cli's new `tx sigsheet-new` creates the Sigsheet file (1,931 bytes; the strict reader accepts it); CCC signs (x0); ckb-cli signs (x1); ckb-cli sends | **committed**: `0xbd095ca9…34e2`, block 50,741 |
| C3 | CCC creates a file for C1's exact transaction | **byte-identical** to ckb-cli's file |
| C2 | CCC builds the transaction and creates the file (1,931 bytes; accepted); ckb-cli signs (x0); CCC signs (x2); CCC finalizes and sends | **committed**: `0xf6f0ab8c…1dd9`, block 50,749 |

The cost: ckb-cli **+91 lines (87 code)** on top of X6's patch ([`ckb-cli-creation.diff`](ckb-cli-creation.diff): `Sigsheet::create` and `tx sigsheet-new`), its own tests **7 passed** with it (`results/ckb-cli-test-with-creation.log`), as before; CCC **59 lines (52 code)** in a separate module (`ccc-create/create.ts`), using X6's patched core unchanged. Creation is the one step that needs a node (each input's previous transaction). Neuron's creation wasn't measured: its export already fetches the input transactions ([background §5](../../background.md#5-neuron-v02041)), and its patch would convert that export.

Source: `results/creation.json`, `results/creation/` (every file, with its SHA-256 in `creation.json`).
