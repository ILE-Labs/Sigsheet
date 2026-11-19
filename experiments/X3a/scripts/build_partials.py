#!/usr/bin/env python3
"""X3a step 1: five one-signature partial transactions for fiber-scripts PR #34, from its real signatures.

Usage, from experiments/X3a:  python3 -I -X utf8 scripts/build_partials.py > results/partials.json

Reads X1's case file (cases/R1-fiber-scripts-pr34.json: the transaction as committed on mainnet, with its
input cells) and X1's copies of the PR's signatures: the deploy file's `cell_tx_signatures` (member 1's
multisig signature and the single-key input's signature) and the four PR comments (one multisig signature
each). Recomputes the multisig group's signing message with X1's independent implementation
(experiments/X1/scripts/ckbcore.py), recovers every signature to a member key hash, and writes one partial
transaction per member in CCC's layout: the multisig lock at its final length (script | M x 65 bytes), the
member's signature in the first slot, zero bytes in the others. The single-key input's signed witness goes
only into the partial of the member who owns that input (member 1, whose key hash is the input's lock args);
every other partial carries that witness's zero-filled placeholder. Nothing goes on any chain.
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
X1 = HERE.parent / "X1"
sys.path.insert(0, str(X1 / "scripts"))
import ckbcore as c  # noqa: E402

case = json.loads((X1 / "cases" / "R1-fiber-scripts-pr34.json").read_text())
tx = case["tx"]
g = next(x for x in case["groups"] if x["kind"] == "multisig")
s = next(x for x in case["groups"] if x["kind"] == "sighash")
args = g["lock"]["args"]
keys = [c.h2b(k) for k in g["multisig"]["key_hashes"]]
M, R = g["multisig"]["threshold"], g["multisig"]["require_first_n"]
script = c.multisig_script(R, M, keys)

# the unsigned witnesses: multisig lock zero-filled at its final length; the single-key lock zero-filled
w0_zero = c.witness_args(script + bytes(65 * M))
w1_zero = c.witness_args(bytes(65))
msg = c.multisig_message(tx, g["input_indices"], [w0_zero, w1_zero])

deploy = json.loads((X1 / "data" / "fiber-scripts-34" / "mainnet.json").read_text())
found = [("deploy file", deploy["cell_tx_signatures"][args][0])]
for i in range(1, 5):
    text = (X1 / "data" / "fiber-scripts-34" / f"comment-{i}.txt").read_text()
    m = re.search(re.escape(args) + r":\s*(0x[0-9a-f]{130})", text)
    found.append((f"comment-{i}", m.group(1)))

sigs = {}
for where, sig in found:
    kh = c.blake160(c.recover(msg, c.h2b(sig)))
    member = keys.index(kh)  # raises if not a member
    sigs[member] = {"source": where, "signature": sig, "key_hash": c.b2h(kh)}

single_sig = deploy["cell_tx_signatures"][s["lock"]["args"]][0]
single_owner = keys.index(c.h2b(s["lock"]["args"]))
w1_signed = c.witness_args(c.h2b(single_sig))

partials = []
for member in sorted(sigs):
    w0 = c.witness_args(script + c.h2b(sigs[member]["signature"]) + bytes(65 * (M - 1)))
    w1 = w1_signed if member == single_owner else w1_zero
    ptx = dict(tx)
    ptx["witnesses"] = [c.b2h(w0), c.b2h(w1)]
    partials.append({"member": member, "carries_single_key_signature": member == single_owner, "tx": ptx})

json.dump({
    "case": case["id"], "tx_hash": case["tx_hash"], "multisig_args": args, "threshold": M, "require_first_n": R,
    "members": [c.b2h(k) for k in keys], "message": c.b2h(msg),
    "signatures_by_member": {str(k): v for k, v in sorted(sigs.items())},
    "single_key_owner_member": single_owner, "single_key_signature": single_sig,
    "single_key_witness_signed": c.b2h(w1_signed), "single_key_witness_placeholder": c.b2h(w1_zero),
    "partials": partials,
}, sys.stdout, indent=1)
