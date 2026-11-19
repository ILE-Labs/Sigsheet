#!/usr/bin/env python3
"""XC4 step 1: extract every multisig WitnessArgs.lock from X1's real and devnet transactions.

Usage, from experiments/XC4:
    python3 -I -X utf8 scripts/extract_locks.py > results/locks.json

Reads X1's saved transactions (mainnet: PR #34 as committed, the genesis 2-of-3 payment; devnet: the 9 committed
cases). A witness lock is taken as a multisig lock when S = 0 and its length is exactly 4 + 20N + 65M
with 0 < M <= N and R <= M, which is the lock's own size rule (ckb-system-scripts 72eb92f,
secp256k1_blake160_multisig_all.c). Prints JSON: one entry per lock with the case, the witness index,
S, R, M, N, the byte length and the hex bytes.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
X1 = HERE.parent.parent / "X1"
sys.path.insert(0, str(X1 / "scripts"))
import ckbcore  # noqa: E402  (X1's Molecule helpers: parse_witness_args)

CASES = [("R1-fiber-scripts-pr34-committed", X1 / "data/mainnet/0x4396de69818bd88b7fce64797ccec25d1294912d56846432f29fd192120992ee.json"),
         ("R2-dao-payout", X1 / "data/mainnet/0x63a7f3a52fc91c52939186ca9c1064238ccdfe498d3398f25707537f591bbaa4.json")]
CASES += [(p.stem, p) for p in sorted((X1 / "data/devnet/committed").glob("*.json"))]


def main():
    out = []
    for case, path in CASES:
        tx = json.loads(path.read_text())["result"]["transaction"]
        for i, w in enumerate(tx["witnesses"]):
            raw = ckbcore.h2b(w)
            if not raw:
                continue
            try:
                lock = ckbcore.parse_witness_args(raw)[0]
            except Exception:
                continue
            if not lock or len(lock) < 4:
                continue
            s, r, m, n = lock[0], lock[1], lock[2], lock[3]
            if s == 0 and 0 < m <= n and r <= m and len(lock) == 4 + 20 * n + 65 * m:
                out.append({"case": case, "witness_index": i, "S": s, "R": r, "M": m, "N": n,
                            "bytes": len(lock), "lock": "0x" + lock.hex()})
    json.dump(out, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
