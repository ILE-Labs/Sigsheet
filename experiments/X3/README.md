# X3: is merging safe in any order, any number of times, with junk? (every candidate format)

**Question:** property tests of the merge every format uses (the merge rule, D11, and the finalize rule, D12): random orders, repeats, duplicates, invalid signatures, non-members and "first R", on the prototypes of C, B (with witnesses) and A. [X3a](../X3a/README.md) tested the rules on PR #34's signatures; this runs the formats themselves, file to file.

## Method

`scripts/x3.py`, on six cases:
- R1, PR #34 (five real member signatures and the single-key one); S6 (two multisig groups) and S7 (multisig plus single key), X1's devnet cases with their committed signatures;
- three new devnet cases from the funded cells (`../X5/data/funding.json`), where every member signs with the prototypes' signer (fresh test keys s1-s5):
  - **S10:** one multisig script [s1, s2, s3] under the genesis and the v2 deployments in one transaction: two lock groups with the same lock args;
  - **S11:** the same script under v2 with 20-byte args and with 28-byte args (a since): two groups, one config;
  - **R1-35:** 3-of-5 [s1..s5] with R = 1 (s1 must sign).

For each lock group, a pool: every valid member signature; its high-s twin; a second valid low-s signature by the same member (another nonce); and junk: 65 random bytes, a valid signature by a non-member, a member's signature over another group's message, over another transaction, filed under the wrong member, and a truncated 64-byte one. Each trial draws 2-6 partial files (the unsigned file plus 1-4 pool entries each), encodes them in the format, and merges them three ways from the encoded bytes: left fold, right fold, and a random tree over a shuffled order. A trial passes if all three give the same bytes; also checked: merging the result with itself or with any input changes nothing; nothing outside the valid pool survives; when ready, the finalized transaction passes the lock's rules in Python. Then: a file for a different transaction must be refused; S10's signatures keyed by args against keyed by lock hash; R1-35 without and with its required member. Finally the three new cases are finalized and sent to the devnet.

## Exact command

From `experiments/X3/` (the devnet must run, the cells must be funded with `../X5/scripts/fund_s4.py`, and the test keys must be in `keys/s4/` at the repository root):

```sh
python3 -I -X utf8 scripts/x3.py 200 > results/x3.json 2> results/x3.log    # R1 runs a quarter of the trials (50)
```

R1 runs fewer trials because its 284 KB previous transaction makes each merge about 0.15 s in pure Python.

**Offline re-run.** `./bench/run.sh` (benchmark `x3`) runs this experiment's own functions on offline copies of the three devnet cases: the same shapes, built from one synthetic previous transaction, with member keys made at run time and never written anywhere ([`bench/lib/offline_x3.py`](../../bench/lib/offline_x3.py)). It checks the same invariants: every trial gives the same bytes from three merge orders, merging is idempotent, no junk survives, and every ready file finalizes into a transaction that passes the lock's rules. By default it runs 20 trials per case and format; `./bench/run.sh --full` runs this README's 200.

## Environment

2026-11-18 21:38 UTC to its end; Python 3.14.4; the prototypes; the local devnet (ckb 0.210.0). Raw output: `results/x3.json`; the three new cases' models: `cases/`.
