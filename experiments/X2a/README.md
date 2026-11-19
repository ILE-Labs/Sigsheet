# X2a: the bytes each format must carry

A first measurement of X2's sizes, for the real cases only, made to settle disputed byte figures (how much hex JSON adds, how much path A's `resolved_inputs` repeats, whether a proof can be trimmed). [X2](../X2/README.md) measures every case and format on the prototypes.

## Question

For the two real cases, how many bytes do the transaction and the previous transactions that prove its input cells take in binary (Molecule) and in hex JSON? How much would path A's `resolved_inputs.outputs_data` repeat? How much does carrying only the previous transactions' raw part (without their witnesses) save?

## Method and command

`scripts/sizes.py` reads X1's saved mainnet data (the PR #34 deploy file's `used_input_txs`, X1's RPC records, X1's case files), recomputes every transaction hash with X1's independent encoder, and measures each piece. From `experiments/X2a/`:

```sh
python3 -I -X utf8 scripts/sizes.py > results/sizes.json
```

Compact JSON means `json.dumps(..., separators=(",", ":"))` of the RPC form (hex numbers and bytes), which is what RFC 8785 would emit for it.

## Runs

- 2026-11-18, first run: compared a binary proof without witnesses with a JSON proof with witnesses.
- 2026-11-18, second run, after a review found the first comparison wasn't like for like: `sizes.py` reports two like-for-like pairs, the proof with its witnesses on both sides and without them on both sides. Same command: `python3 -I -X utf8 scripts/sizes.py > results/sizes.json`. `results/sizes.json` is from this run.

## Environment

2026-11-18 (UTC); Python 3.14; X1's `ckbcore.py`; mainnet data fetched by X1 from `https://mainnet.ckb.dev/` on 2026-11-18. No network calls.
