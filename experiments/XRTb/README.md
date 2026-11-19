# XRTb: attacks and objections considered, second round

**Question:** a second round of attacks and objections says the design's earlier rules mishandle some transactions or can be attacked. Which hold, measured on the local devnet or with the prototypes, and does each candidate rule fix it? How the design answers each: [design record §5](../../design-record.md#5-security-analysis).

| Part | What it measures | Where it runs |
|---|---|---|
| XRTb-1 `scripts/genesis_r.py` | The genesis rule with a required member at position 10; a set no order fixes | devnet: `test_tx_pool_accept` (the node's full verification; nothing committed) |
| XRTb-2 `scripts/rule_checks.py` | A conflict in a group the reader doesn't sign; Omnilock's multisig mode carried; tokens and change labels; configs for no input; single-key args | the prototypes, offline; keys made at run time, never stored |
| XRTb-3 `scripts/dao_flow.py` | The fee of a Nervos DAO withdrawal of several deposits; maturity | devnet: a two-deposit Nervos DAO withdrawal, committed |

**Method.** Fresh test keys only: XRTb-1 uses XRT-1's `keys/xrt/`; XRTb-3 makes `keys/xrtb/` (three members of a v2 2-of-3); XRTb-2's keys exist only while it runs. `keys` is a link at the repository root to a folder outside the checkout, and the scripts refuse to write keys inside it. The prototypes ([`../prototypes/`](../prototypes/README.md)) are used unchanged; the simpler rules and the candidate rules are written in the scripts, as in XRT.

The fee rules XRTb-3 compares, for each Nervos DAO withdrawing input (RFC 0023: (c_t − c_o) × AR_n / AR_m + c_o, with AR_m from the deposit header the witness's `input_type` names):
- **naive:** inputs minus outputs;
- **an upper bound:** AR_n is the largest accumulated rate among the other header deps;
- **inclusion proofs** (the design's rule): the withdrawing cell's previous transaction comes with CKB's transaction proof (`get_transaction_proof`), verified offline (the CBMT root of the transaction hashes, then `transactions_root = merge(raw root, witnesses_root)`) against a carried header, so AR_n is that block's; the minimal since follows from [`dao.c` L202-L241](https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c#L202-L241).

Each is compared with the fee the node reports for the same transaction (`test_tx_pool_accept`) and with `calculate_dao_maximum_withdraw`.

## Exact commands

From `experiments/XRTb/`, with X1's devnet running (for XRTb-1 and XRTb-3):

```sh
mkdir -p results
python3 -I -X utf8 scripts/genesis_r.py > results/genesis-r.json 2> results/genesis-r.log
python3 -I -X utf8 scripts/rule_checks.py > results/rule-checks.json 2> results/rule-checks.log
# about 30 minutes on a devnet with 10-block epochs (180 epochs must pass):
python3 -I -X utf8 scripts/dao_flow.py > results/dao-flow.json 2> results/dao-flow.log
```

The first start of `dao_flow.py` stopped before sending anything: the deposit transaction lacked the DAO code as a cell dep (`ScriptNotFound`); `fund_dao` adds it.

`./bench/run.sh` (benchmark `xrtb2`) re-runs XRTb-2 offline and compares every outcome with `results/rule-checks.json`.

## Environment

2026-11-19 (UTC); local devnet (ckb 0.210.0; epoch length 10 blocks; the genesis multisig binary byte-identical to mainnet's, the 2024 and v2 binaries copied from mainnet, as in X1); Python 3.14.4. Nothing was sent anywhere but the local devnet.

## Files

`scripts/`, `results/` (JSON and logs), `results.md`.
