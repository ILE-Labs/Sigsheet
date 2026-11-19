# XRTb results: attacks and objections, second round, measured

Conditions (design-stage): 2026-11-19 (UTC); local devnet (ckb 0.210.0, epoch length 10 blocks; the genesis multisig binary byte-identical to mainnet's, the 2024 and v2 binaries copied from mainnet); fresh test keys; the design-stage prototypes unchanged. Commands: `README.md`. Raw output: `results/`. How the design answers each: [design record §5](../../design-record.md#5-security-analysis).

"The simpler rules" are the design's rules before these checks (called version 2 in the scripts); "the design's rules" are the ones it keeps ([design record §3](../../design-record.md#3-the-design-decisions-with-their-evidence)).

## XRTb-1. The genesis binary with a required member, and a set no order fixes

| Case (genesis, N = 12) | Set | Member order | Descending order |
|---|---|---|---|
| A. M = 11, R = 11 | members 0-10 (position 10 required) | **accepted** | **accepted** |
| B. M = 2, R = 0 | {5, 10} | rejected | rejected |
| | {10, 11} | rejected | rejected |
| | {5, 11} | accepted | accepted |
| C1. M = 10, R = 10 | members 0-9 | accepted | accepted |
| C2. M = 11, R = 0 | members 0-9 and 11 | accepted | accepted |

Source: `results/genesis-r.json` (funding transaction in the file; `test_tx_pool_accept`, nothing committed). Every rejection is "TransactionFailedToVerify" on `Inputs[0].Lock`.

- **A required member at position 10 is never skipped:** R ≤ M, so R = 11 means M ≥ 11, and the binary accepted position 10 there, as in every member-order set with position 10 and M ≥ 11 in XRT-1's data (N = 11 to 24).
- **For M ≤ 10, no order rescues position 10:** with M = 2 there are only two orders, and both were rejected for both sets that include position 10. A finalizer can't use that signature on the genesis binary; the group needs another member's.

## XRTb-2. The simpler rules against the design rules, offline

| Check | The simpler rule | The design's rule |
|---|---|---|
| An honest copy with member K3's valid signature in a group the reader doesn't sign, and a copy with 65 zero bytes under K3 | the merge keeps the **zero bytes** (the smaller), in both orders; the reader that signs the kind then **can't finalize** ("single-key group … has no signature") | the merge is **refused**, in both orders; the honest copy alone carries the signature and finalizes; a reader that signs the kind merges both copies and finalizes, and the lock's rules pass |
| 50 configs that hash to their keys but belong to no input | all 52 configs kept; the file grows from **2,685 to 14,585 bytes** with the **same unsigned id** | 2 kept (the multisig's, and Omnilock's, whose key occurs at args bytes 1-20) |
| An Omnilock multisig-mode group (args 22 bytes, flag 6, the config key at bytes 1-20) next to a v2 multisig group | the multisig checks run on the multisig group only; the Omnilock group is **carried**; its config is kept; partial finalize writes the multisig witness, leaves Omnilock's as the template, and the multisig lock's rules pass | the same; the config is kept by the config rule too |
| A single-key input with 32-byte args | the file is **accepted**; its key's signature is dropped as "doesn't verify … or not a member" | refused: the lock requires 20 bytes ([sighash_all.c L106-L107](https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_sighash_all.c#L106-L107)) |
| A transaction that consumes a 1,000,000-unit xUDT cell with no token output | shown: two inputs (the token cell's type script only), the multisig output as **change**, "fee: 0.001 CKB" | the input's data and **"xUDT amount 1,000,000"**; "warning: input 1's type script … appears on no output: its cell is consumed (xUDT amount 1,000,000 leaves)" |
| PR #34's shape (a multisig input next to a single-key input whose change goes back to it) | the single-key change is labelled a **payment** | "back to the lock of input 1" |

Source: `results/rule-checks.json`. The first version of the prototype refuses the Omnilock and no-input-config files outright ("a multisig config that no input uses"); the simpler rules relaxed that, which is what the no-input-config check attacks. `./bench/run.sh` (benchmark `xrtb2`) re-runs these checks offline, with keys made at run time, and compares every outcome.

## XRTb-3. A Nervos DAO withdrawal of two deposits

A v2 2-of-3 multisig (fresh test keys) deposited 2,000 CKB (block 62,540) and 3,000 CKB (block 62,543), started both withdrawals in blocks 62,546 and 63,546 (phase 1, 100 epochs apart), and withdrew both in one phase-2 transaction with header deps [D1, D2, W1, W2]: **committed**, `0xcf852daf…8735`, block 64,357 (3,155,574 cycles). A second phase-2 transaction, with its output cut to the deposited 5,000 CKB minus 0.001, was only dry-run (accepted). The node's own fee (`test_tx_pool_accept`) is the reference.

| Rule (what a reader shows as the fee) | The withdrawal sent (node: **0.001 CKB**) | The output cut (node: **7.12722788 CKB**) |
|---|---|---|
| inputs − outputs | −7.12522788 | 0.001 (7.12622788 hidden) |
| an upper bound: the largest rate among the other header deps | 4.63600414 (overstated by 4.63500414) | 11.76223202 (overstated by 4.63500414) |
| **the design's rule: inclusion proofs** (CKB's transaction proofs, verified offline) | **0.001, the node's figure** | **7.12722788, the node's figure** |

- **Per input:** with the proofs, each withdrawable amount equals the node's `calculate_dao_maximum_withdraw` exactly (2,000.02791696 and 3,007.09831092 CKB); the upper bound took input 0 at W2's rate (2,004.66292110). The minimal since computed from the proven headers ([dao.c L202-L241](https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c#L202-L241)) equals the since the node accepted (`0x20000a0000001922`, `0x20000a0003001922`).
- **The proofs:** both phase-1 transactions' proofs verify offline against their headers' `transactions_root`; the same proof with its block hash changed to the deposit block's fails. In a five-transaction block (63,697, made for this check, `results/cbmt-check.json`), all five transactions' proofs (2 or 3 lemmas) verify, and a proof checked against another transaction's hash fails.
- **So:** a reader that takes each withdrawing block only from a proof that verifies shows the node's fee; without the proofs it can only show an upper bound, which is safe (it never understates) but wrong for an honest withdrawal of several deposits. This is design-stage: the rule was measured on the prototypes, not in the wallet patches, and phase 1's acceptance test 10 checks it on the implementations ([design record §8.2](../../design-record.md#82-acceptance-tests)).

Sources: `results/dao-flow.json` (every transaction, header, proof and rule), `results/dao-flow.log`, `results/cbmt-check.json`.
