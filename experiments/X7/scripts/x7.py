#!/usr/bin/env python3
"""X7: the numbers. File sizes, how long reading, verifying, merging and finalizing take, and the limits that matter.

Usage, from experiments/X7:  python3 -I -X utf8 scripts/x7.py > results/x7.json
1. Sizes: every case and format from X2's results, plus the smallest thing a signer can post: one signature with
   the ids that place it (unsigned transaction id, lock group, signer), as canonical JSON.
2. Times in the Python prototypes (median of 5 runs): decode + validate; the messages; a two-file merge; a merge of
   one file per signature; finalize.
3. Times in the patched wallets on the largest real case (PR #34, 733 KB as C): ckb-cli and CCC merging two partial
   files and finalizing, offline (median of 3 process runs, so they include the process start).
4. Sizes against the limits that matter: CKB's tx-pool size limit, the lock's witness bound, relay message limits.
"""
import json
import os
import pathlib
import statistics
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
EXP = HERE.parent
INV = EXP.parent
sys.path.insert(0, str(EXP / "prototypes"))
import core  # noqa: E402
import fmt_a  # noqa: E402
import fmt_b  # noqa: E402
import fmt_c  # noqa: E402
from core import c  # noqa: E402

NET = "0x" + "00" * 32
FMT = {"C": (fmt_c.encode, fmt_c.decode), "B+w": (lambda m: fmt_b.encode(m, NET, True), lambda b: fmt_b.decode(b)[0]),
       "A": (fmt_a.encode, fmt_a.decode)}
CKBCLI = EXP / "X6" / "ckb-cli" / "src-copy" / "target" / "debug" / "ckb-cli"
CCC = EXP / "X6" / "ccc" / "harness"
ENV = {**os.environ, "npm_config_cache": str(INV / "refs" / "_npm-cache"), "CKB_CLI_HOME": str(INV / "keys" / "ckb-cli-home-s4")}


def med(fn, n=5):
    ts = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t0)
    return round(statistics.median(ts) * 1000, 2)


def load(name):
    d = json.loads((EXP / "X2" / "cases" / name).read_text())
    m = d["model"]
    return core.Model(m["tx"], m["prevs"], m["configs"], m["sigs"])


def split(m):
    """One file per signature (the way signers each post their own)."""
    out = []
    for gh, box in m.sigs.items():
        for kh, s in box.items():
            p = m.copy()
            p.sigs = {gh: {kh: s}}
            out.append(p)
    return out


def main():
    out = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "python": sys.version.split()[0]}
    x2 = json.loads((EXP / "X2" / "results" / "x2.json").read_text())
    out["sizes"] = {f: {cid: v["bytes"] for cid, v in x2["summary"][f].items()} for f in ("C", "B", "B+w", "A", "A-json-view")}
    out["sizes_zlib9"] = {f: {cid: v["bytes_zlib9"] for cid, v in x2["summary"][f].items()} for f in ("C", "B+w", "A")}
    times, frag = {}, {}
    for f in sorted((EXP / "X2" / "cases").glob("*.json")):
        m = load(f.name)
        cid = f.stem
        uid = m.unsigned_id()
        gh, box = next(iter(m.sigs.items()))
        kh, s = next(iter(box.items()))
        frag[cid] = len(core.canon({"lock_group": gh, "signature": s, "signer": kh, "unsigned_id": uid}))
        t = {}
        for name, (enc, dec) in FMT.items():
            data = enc(m)
            parts = [enc(p) for p in split(m)]
            half = len(parts) // 2 or 1
            a = enc(core.merge(*[dec(p) for p in parts[:half]])) if len(parts) > 1 else parts[0]
            b = enc(core.merge(*[dec(p) for p in parts[half:]])) if len(parts) > 1 else parts[0]
            ready = all(x["ready"] for x in core.status(m).values())
            t[name] = {
                "decode_validate_ms": med(lambda: core.validate(dec(data))),
                "messages_ms": med(lambda: [core.group_message(m, g) for g in core.lock_groups(m).values()
                                            if g["kind"] != "unknown"]),
                "merge_two_files_ms": med(lambda: enc(core.merge(dec(a), dec(b)))),
                "merge_one_file_per_signature_ms": med(lambda: enc(core.merge(*[dec(p) for p in parts])), 3),
                "files_merged": len(parts),
                "finalize_ms": med(lambda: core.finalize(m)) if ready else None,
            }
        times[cid] = t
    out["python_times"] = times
    out["signature_fragment_bytes"] = frag
    # wallets on PR #34, offline
    r1 = load("R1-fiber-scripts-pr34.json")
    parts = split(r1)
    tmp = pathlib.Path(tempfile.mkdtemp(dir=HERE / "results"))
    fa, fb = tmp / "r1-a.json", tmp / "r1-b.json"
    fa.write_bytes(fmt_c.encode(core.merge(*parts[:3])))
    fb.write_bytes(fmt_c.encode(core.merge(*parts[3:])))
    tools = {}

    def run(args, cwd=None):
        t0 = time.perf_counter()
        p = subprocess.run(args, cwd=cwd, env=ENV, capture_output=True, text=True)
        return time.perf_counter() - t0, p

    for label, args, cwd in [
        ("ckb-cli merge two PR #34 files", [str(CKBCLI), "tx", "sigsheet-merge", "--sigsheet", str(fa), "--sigsheet",
                                            str(fb), "--output", str(tmp / "k-m.json")], None),
        ("ckb-cli finalize PR #34", [str(CKBCLI), "tx", "sigsheet-send", "--sigsheet", str(tmp / "k-m.json"),
                                     "--output", str(tmp / "k-final.json")], None),
        ("CCC merge two PR #34 files", ["npx", "tsx", "sigsheet-ccc.ts", "merge", str(tmp / "c-m.json"), str(fa),
                                        str(fb)], CCC),
        ("CCC finalize PR #34", ["npx", "tsx", "sigsheet-ccc.ts", "finalize", str(tmp / "c-m.json"),
                                 str(tmp / "c-final.json")], CCC),
    ]:
        runs = [run(args, cwd) for _ in range(3)]
        tools[label] = {"median_s": round(statistics.median(r[0] for r in runs), 2), "rc": runs[-1][1].returncode,
                        "stdout": runs[-1][1].stdout.strip()[-200:], "stderr": runs[-1][1].stderr.strip()[-200:]}
    merged_same = (tmp / "k-m.json").read_bytes() == (tmp / "c-m.json").read_bytes()
    tools["ckb-cli and CCC merges identical"] = merged_same
    final = json.loads((tmp / "k-final.json").read_text())
    tools["final tx hash"] = c.b2h(c.tx_hash(final))
    tools["final passes lock rules"] = all(core.lock_rule_check(
        {k: final[k] for k in core.RAW_FIELDS + ("witnesses",)}, r1.prevs).values())
    out["wallet_times_pr34"] = tools
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()
    # limits
    final_bytes = len(core.canon(core.finalize(r1)))
    full_tx = c.table([c.raw_transaction(core.finalize(r1)), c.dynvec([c.mol_bytes(c.h2b(w)) for w in core.finalize(r1)["witnesses"]])])
    out["limits"] = {
        "ckb_tx_pool_size_limit_bytes": 512_000,
        "pr34_final_transaction_molecule_bytes": len(full_tx),
        "pr34_final_transaction_json_bytes": final_bytes,
        "lock_witness_limit_bytes": 32_768,
        "largest_multisig_lock_bytes": 4 + 20 * 255 + 65 * 255,
        "nip11_relay_message_limits_seen": [16_384, 65_535, 524_288],
        "pr34_file_bytes_C": out["sizes"]["C"]["R1-fiber-scripts-pr34"],
        "pr34_signature_fragment_bytes": frag["R1-fiber-scripts-pr34"],
    }
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
