#!/usr/bin/env python3
"""X1 numbers: how many bytes of the fiber-scripts PR #34 deploy file each top-level field takes, as stored.

Usage, from experiments/X1:  python3 -I -X utf8 scripts/measure_pr34.py
Reads data/fiber-scripts-34/mainnet.json (fetched from fiber-scripts at 026027f; see README.md), checks
its SHA-256 against the file at fiber-scripts commit 026027f, and walks the top-level JSON object
with json.JSONDecoder.raw_decode to find the exact byte span of each field's value in the file
(nothing is re-serialized). Also measures each transaction inside used_input_txs (one of them may be cell_tx itself, kept for
the dep group step) and the bytes of their outputs_data, and which of them prove cell_tx's own inputs.
Writes results/pr34-size.json.
"""
import datetime
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent.parent
FILE = HERE / "data" / "fiber-scripts-34" / "mainnet.json"
# The SHA-256 of deployment/mainnet/mainnet.json at fiber-scripts commit 026027f54f6a90cb48d8cc184b230e2018bb8611.
EXPECTED_SHA256 = "8563ba8dcd0d051822dd0cc21db995dc8e6a2984e900d3500068f0185a07b51e"


def spans(text):
    """Byte span of each top-level member's value, in file order. The file is ASCII, so chars = bytes."""
    dec = json.JSONDecoder()
    ws = " \t\r\n"
    i = 0
    while text[i] in ws:
        i += 1
    assert text[i] == "{"
    i += 1
    out = []
    while True:
        while text[i] in ws:
            i += 1
        if text[i] == "}":
            return out
        key, i = dec.raw_decode(text, i)
        while text[i] in ws:
            i += 1
        assert text[i] == ":"
        i += 1
        while text[i] in ws:
            i += 1
        start = i
        value, i = dec.raw_decode(text, i)
        out.append((key, start, i, value))
        while text[i] in ws:
            i += 1
        if text[i] == ",":
            i += 1


def main():
    raw = FILE.read_bytes()
    text = raw.decode("ascii")
    sha = hashlib.sha256(raw).hexdigest()
    members = spans(text)
    fields = {k: e - s for k, s, e, _ in members}
    used = next(v for k, _, _, v in members if k == "used_input_txs")
    us, ue = next((s, e) for k, s, e, _ in members if k == "used_input_txs")
    entry_bytes = {k: e - s for k, s, e, _ in spans(text[us:ue])}
    cell_tx = next(v for k, _, _, v in members if k == "cell_tx")
    needed = sorted({i["previous_output"]["tx_hash"] for i in cell_tx["inputs"]})
    od = {h: sum(len(d) // 2 - 1 for d in tx["outputs_data"]) for h, tx in used.items()}
    total = len(raw)
    report = {
        "file": str(FILE.relative_to(HERE)),
        "measured": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "sha256": sha,
        "sha256_matches_the_pinned_file": sha == EXPECTED_SHA256,
        "file_bytes": total,
        "field_value_bytes_in_file": fields,
        "used_input_txs_share_of_file": round(fields["used_input_txs"] / total, 4),
        "cell_tx_share_of_file": round(fields["cell_tx"] / total, 4),
        "used_input_txs_count": len(used),
        "used_input_txs_entry_bytes_in_file": entry_bytes,
        "cell_tx_input_tx_hashes": needed,
        "bytes_proving_cell_tx_inputs": sum(entry_bytes[h] for h in needed),
        "share_proving_cell_tx_inputs": round(sum(entry_bytes[h] for h in needed) / len(raw), 4),
        "used_input_txs_outputs_data_bytes_decoded": od,
    }
    (HERE / "results" / "pr34-size.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
