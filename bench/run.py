"""Re-run the design-stage benchmarks that work offline and compare each value with the recorded one.

Run it with ./bench/run.sh from the repository root (see bench/README.md). Standard library only; no network;
nothing outside this checkout is written. Results go to bench/out/ (or --out DIR): summary.md, summary.json and
each benchmark's raw output. The recorded design-stage values are the experiments' own result files
(experiments/*/results/), which this script only reads.

Statuses: PASS (a deterministic value equals the recorded one), FAIL (it doesn't), INFO (a time, measured on
this machine, shown for reference only), SKIP (an input this checkout doesn't have, with the step that adds it).
"""
import argparse
import json
import os
import pathlib
import platform
import re
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXP = ROOT / "experiments"
sys.path.insert(0, str(ROOT / "bench" / "lib"))
sys.path.insert(0, str(EXP / "prototypes"))
sys.path.insert(0, str(EXP / "X1" / "scripts"))

ROWS = []
MAINNET_FILES = [
    "X1/cases/R1-fiber-scripts-pr34.json", "X1/cases/R2-dao-payout.json",
    "X2/cases/R1-fiber-scripts-pr34.json", "X2/cases/R2-dao-payout.json",
    "X3a/results/partials.json",
    "X6/interop/a-check/R1-fiber-scripts-pr34.c.json", "X6/interop/a-check/R2-dao-payout.c.json",
    "X1/data/fiber-scripts-34/mainnet.json",
    "X1/data/mainnet/0x63a7f3a52fc91c52939186ca9c1064238ccdfe498d3398f25707537f591bbaa4.json",
]
NEEDS_MAINNET = "needs the mainnet inputs (./bench/fetch-mainnet.sh, or experiments/mainnet-inputs.md)"


def row(bench, measure, recorded, measured, status):
    ROWS.append({"benchmark": bench, "measure": measure, "recorded": recorded, "measured": measured,
                 "status": status})


def check(bench, measure, recorded, measured):
    row(bench, measure, recorded, measured, "PASS" if recorded == measured else "FAIL")


def recorded(rel):
    return json.loads((EXP / rel).read_text())


def have_mainnet():
    return all((EXP / f).exists() for f in MAINNET_FILES)


def run_script(script, args=(), cwd=None, timeout=3600):
    """Run one experiment script as it is; return its JSON output (stdout)."""
    p = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str(script), *map(str, args)],
                       cwd=str(cwd or script.parent.parent), capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"{script.name} exited {p.returncode}: {p.stderr.strip()[-400:]}")
    return json.loads(p.stdout)


def save(out, name, data):
    (out / name).write_text(json.dumps(data, indent=1, sort_keys=True, default=str))


# ---------------------------------------------------------------- X1: the signing message, independent implementation

def bench_x1(out, full):
    import ckbcore as c
    rec = recorded("X1/results/python.json")["messages"]
    measured, equal, total = {}, 0, 0
    for f in sorted((EXP / "X1" / "cases").glob("*.json")):
        case = json.loads(f.read_text())
        ok_hash = c.b2h(c.tx_hash(case["tx"])) == case["tx_hash"]
        check("X1", f"{case['id']}: transaction hash recomputed", True, ok_hash)
        tx = case["tx"]
        w = [c.h2b(x) for x in tx["witnesses"]]
        for g in case["groups"]:
            idx = g["input_indices"]
            if g["kind"] == "multisig":
                msg = c.multisig_message(tx, idx, w)
            else:
                msg = c.sighash_all_message(tx, idx, w, c.sighash_zeroed_first_witness(w[idx[0]]))
            measured.setdefault(case["id"], {})[g["name"]] = c.b2h(msg)
            total += 1
            equal += rec.get(case["id"], {}).get(g["name"]) == c.b2h(msg)
    save(out, "x1-messages.json", measured)
    n_rec = sum(len(v) for k, v in rec.items() if k in measured)
    check("X1", "lock groups whose message equals the recorded one (independent implementation)",
          f"{n_rec} of {n_rec}", f"{equal} of {total}")
    if not have_mainnet():
        row("X1", "R1 and R2 (mainnet cases)", "3 lock groups", "-", "SKIP: " + NEEDS_MAINNET)


# ---------------------------------------------------------------- X2: round trips, sizes, the C4 mapping, the boundary

def bench_x2(out, full):
    rec = recorded("X2/results/x2.json")
    m = run_script(EXP / "X2" / "scripts" / "x2.py", cwd=EXP / "X2")
    save(out, "x2.json", m)
    present = [c["id"] for c in m["cases"]]
    for fmt in ("C", "B", "B+w", "A", "A-json-view"):
        for cid in present:
            r, v = rec["summary"][fmt][cid], m["summary"][fmt][cid]
            check("X2", f"{fmt} {cid}: bytes (zlib 9)", f"{r['bytes']:,} ({r['bytes_zlib9']:,})",
                  f"{v['bytes']:,} ({v['bytes_zlib9']:,})")
            if r["lossless"] is not None:
                rr = {k: r[k] for k in ("lossless", "messages_match_expected", "signatures_verified",
                                        "finalized_lock_rules_pass")}
                vv = {k: v[k] for k in rr}
                check("X2", f"{fmt} {cid}: lossless, messages, signatures, finalize", rr, vv)
    rc = {c["id"]: c for c in rec["cases"]}
    for c in m["cases"]:
        check("X2", f"C4 mapping C<->A, {c['id']}", rc[c["id"]]["c4_mapping"], c["c4_mapping"])
        for fmt, d in c["formats"].items():
            if "canonical_reencode" in d:
                check("X2", f"{fmt} {c['id']}: canonical re-encoding", rc[c["id"]]["formats"][fmt]["canonical_reencode"],
                      d["canonical_reencode"])
    for fmt in ("C", "B", "B+w", "A"):
        check("X2", f"{fmt}: the message computation reads only the transaction, previous transactions and config",
              {"holds": rec["boundary"][fmt]["holds"], "other_fields": rec["boundary"][fmt]["other_fields"]},
              {"holds": m["boundary"][fmt]["holds"], "other_fields": m["boundary"][fmt]["other_fields"]})
    if not have_mainnet():
        row("X2", "R1 (PR #34) and R2 (the genesis 2-of-3 payment)", "2 of 12 cases", "-", "SKIP: " + NEEDS_MAINNET)


# ---------------------------------------------------------------- X3: merging in any order (offline copies of the devnet cases)

def bench_x3(out, full):
    import offline_x3
    rec = recorded("X3/results/x3.json")
    trials = rec.get("trials_per_case_and_format", 200) if full else 20
    m = offline_x3.run(trials, include_r1=have_mainnet())
    save(out, "x3-offline.json", m)
    for name, res in m["cases"].items():
        for fmt in ("C", "B+w", "A"):
            d = res[fmt]
            t = d["trials"]
            check("X3", f"{name} {fmt}: trials giving the same bytes from three merge orders", f"{t} of {t}",
                  f"{d['same_bytes_all_three_merges']} of {t}")
            check("X3", f"{name} {fmt}: idempotent and junk-free trials", f"{t} and {t}",
                  f"{d['idempotent']} and {d['junk_free']}")
            check("X3", f"{name} {fmt}: ready trials whose final transaction passes the lock's rules",
                  f"{d['ready']} of {d['ready']}", f"{d['finalized_pass_lock_rules']} of {d['ready']}")
        check("X3", f"{name}: a file for another transaction is refused", True, res["different_transaction_refused"])
    check("X3", "S10 keyed by lock args: signatures under one key", [6], m["S10_keyed_by_args"])
    check("X3", "S10 keyed by lock group: signatures per group", [3, 3], m["S10_keyed_by_lock_hash"])
    fr = rec["first_r"]
    check("X3", "R1-35 (R = 1) without its required member: ready", fr["ready_without_s1"], m["first_r"]["ready_without_s1"])
    check("X3", "R1-35 without its required member: finalize refused",
          fr["finalize_without_s1"].split(": ")[-1], m["first_r"]["finalize_without_s1"].split(": ")[-1])
    check("X3", "R1-35 with all five: members picked", fr["picked_member_indices"], m["first_r"]["picked_member_indices"])
    check("X3", "S10, S11, R1-35 finalized: the lock's rules pass", {k: True for k in m["finals_pass_lock_rules"]},
          m["finals_pass_lock_rules"])
    if not full:
        row("X3", "trials per case and format (R1: a quarter)", rec.get("trials_per_case_and_format"), trials,
            "INFO: fewer trials than recorded; --full runs the recorded count")
    if not have_mainnet():
        row("X3", "R1 (PR #34's real signatures)", "50 trials per format", "-", "SKIP: " + NEEDS_MAINNET)


# ---------------------------------------------------------------- X3a: four merge rules on PR #34's real signatures

def bench_x3a(out, full):
    if not have_mainnet():
        row("X3a", "four merge rules on PR #34's five real signatures", "2,000 trials", "-", "SKIP: " + NEEDS_MAINNET)
        return
    rec = recorded("X3a/results/merge-rules.json")
    trials = rec.get("trials", 2000)
    m = run_script(EXP / "X3a" / "scripts" / "merge_rules.py", [trials], cwd=EXP / "X3a")
    save(out, "x3a-merge-rules.json", m)
    for name, d in rec["rules"].items():
        check("X3a", f"rule {name}: same result both ways, failed merges, invalid final locks", d, m["rules"][name])
    check("X3a", "with only the real signatures", rec["rules_with_only_real_signatures"], m["rules_with_only_real_signatures"])
    check("X3a", "candidate rule idempotent (trials)", rec["reference_idempotent_trials"], m["reference_idempotent_trials"])
    keep = lambda d: {k: v for k, v in d.items() if "chosen members" not in k}  # noqa: E731
    check("X3a", "first R (R = 2, M = 3, N = 5, keys made at run time)", keep(rec["require_first_n_test"]),
          keep(m["require_first_n_test"]))


# ---------------------------------------------------------------- X4: the offline attacks

def bench_x4(out, full):
    if not have_mainnet():
        row("X4", "each attack in each format (base case: R2, the genesis 2-of-3 payment)", "every attack caught", "-",
            "SKIP: " + NEEDS_MAINNET)
        return
    rec = recorded("X4/results/x4.json")
    m = run_script(EXP / "X4" / "scripts" / "x4.py", cwd=EXP / "X4")
    save(out, "x4.json", m)
    for ra, ma in zip(rec["attacks"], m["attacks"]):
        check("X4", f"attack {ra['attack']}: outcome in C, B+w, A",
              {f: r.get("outcome") for f, r in ra["results"].items()},
              {f: r.get("outcome") for f, r in ma["results"].items()})
    check("X4", "honest file: fee (shannons)", rec["honest_fee_shannons"], m["honest_fee_shannons"])
    for k in rec:
        if k.startswith("merge_honest"):
            check("X4", k.replace("_", " "), rec[k], m.get(k))


# ---------------------------------------------------------------- X7: sizes and prototype times

def bench_x7(out, full):
    sys.path.insert(0, str(EXP / "X7" / "scripts"))
    import x7
    import core
    rec = recorded("X7/results/x7.json")
    res = {}
    for f in sorted((EXP / "X2" / "cases").glob("*.json")):
        m = x7.load(f.name)
        cid = f.stem
        uid = m.unsigned_id()
        gh, box = next(iter(m.sigs.items()))
        kh, s = next(iter(box.items()))
        frag = len(core.canon({"lock_group": gh, "signature": s, "signer": kh, "unsigned_id": uid}))
        check("X7", f"{cid}: one posted signature with the ids that place it (bytes)",
              rec["signature_fragment_bytes"][cid], frag)
        enc, dec = x7.FMT["C"]
        data = enc(m)
        parts = [enc(p) for p in x7.split(m)]
        half = len(parts) // 2 or 1
        a = enc(core.merge(*[dec(p) for p in parts[:half]])) if len(parts) > 1 else parts[0]
        b = enc(core.merge(*[dec(p) for p in parts[half:]])) if len(parts) > 1 else parts[0]
        ready = all(x["ready"] for x in core.status(m).values())
        t = {"decode_validate_ms": x7.med(lambda: core.validate(dec(data))),
             "merge_two_files_ms": x7.med(lambda: enc(core.merge(dec(a), dec(b)))),
             "finalize_ms": x7.med(lambda: core.finalize(m)) if ready else None}
        res[cid] = t
        r = rec["python_times"][cid]["C"]
        for k, v in t.items():
            if v is not None:
                row("X7", f"{cid}, format C: {k.replace('_ms', '')} (ms, this machine)", r[k], v,
                    "INFO: time on this machine, for reference")
    save(out, "x7-times.json", res)
    if not have_mainnet():
        row("X7", "R1 and R2 sizes and times", "-", "-", "SKIP: " + NEEDS_MAINNET)


# ---------------------------------------------------------------- X2a: the bytes of the real cases

def bench_x2a(out, full):
    if not have_mainnet():
        row("X2a", "bytes of the transaction and its proof, binary and hex JSON", "PR #34, the genesis 2-of-3 payment", "-",
            "SKIP: " + NEEDS_MAINNET)
        return
    rec = recorded("X2a/results/sizes.json")
    m = run_script(EXP / "X2a" / "scripts" / "sizes.py", cwd=EXP / "X2a")
    save(out, "x2a-sizes.json", m)
    for k in rec:
        check("X2a", k, rec[k], m.get(k))


# ---------------------------------------------------------------- XC4: the CKB IDL documents

def bench_xc4(out, full):
    sys.path.insert(0, str(EXP / "XC4" / "scripts"))
    import make_idls
    with tempfile.TemporaryDirectory() as tmp:
        make_idls.OUT = pathlib.Path(tmp)
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            make_idls.main()
        for f in sorted((EXP / "XC4" / "idl").glob("*.json")):
            g = pathlib.Path(tmp) / f.name
            check("XC4", f"IDL document {f.name}: canonical bytes, identical to the one tested",
                  f"{f.stat().st_size:,} bytes", f"{g.stat().st_size:,} bytes" + ("" if g.read_bytes() == f.read_bytes()
                                                                                  else " (different bytes)"))


# ---------------------------------------------------------------- XRT-2 and XRTb-2: the offline rule checks

def strip_times(d):
    if isinstance(d, dict):
        return {k: strip_times(v) for k, v in d.items() if not re.search(r"(seconds|_s$|_ms$|time)", k)}
    if isinstance(d, list):
        return [strip_times(x) for x in d]
    return d


def bench_xrt2(out, full):
    rec = recorded("XRT/results/prototype-checks.json")
    m = run_script(EXP / "XRT" / "scripts" / "prototype_checks.py", cwd=EXP / "XRT")
    save(out, "xrt2-prototype-checks.json", m)
    for k, r in rec.items():
        v = m.get(k, {})
        if "error" in v and not have_mainnet():
            row("XRT-2", k, "-", "-", "SKIP: " + NEEDS_MAINNET)
            continue
        check("XRT-2", f"{k}: outcome", strip_times(r), strip_times(v))
        for tk in ("prototype_seconds", "candidate_rule_seconds"):
            if tk in r:
                row("XRT-2", f"{k}: {tk.replace('_', ' ')} (this machine)", r[tk], v.get(tk),
                    "INFO: time on this machine, for reference")


def bench_xrtb2(out, full):
    rec = recorded("XRTb/results/rule-checks.json")
    m = run_script(EXP / "XRTb" / "scripts" / "rule_checks.py", cwd=EXP / "XRTb")
    save(out, "xrtb2-rule-checks.json", m)
    hexes = re.compile(r"^0x[0-9a-f]{8,}$")

    def norm(d):
        """Keys are made at run time, so hashes and keys differ from run to run; outcomes and sizes must not.
        Hex values become "0x…", and a map keyed by hex hashes becomes the sorted list of its values."""
        if isinstance(d, dict):
            if d and all(isinstance(k, str) and hexes.match(k) for k in d):
                return sorted((norm(v) for v in d.values()), key=lambda v: json.dumps(v, sort_keys=True))
            return {k: norm(v) for k, v in d.items()}
        if isinstance(d, list):
            return [norm(x) for x in d]
        if isinstance(d, str):
            return re.sub(r"0x[0-9a-f]{8,}", "0x…", d)
        return d
    for k in rec:
        if k in ("conditions", "previous_tx"):
            continue
        check("XRTb-2", f"{k}: outcome", norm(rec[k]), norm(m.get(k)))


# ---------------------------------------------------------------- X6: the size of each wallet's change

def bench_x6(out, full):
    import line_count
    rec = recorded("X6/results/measure.json")
    for name, path in (("ckb-cli", "X6/ckb-cli/patch.diff"), ("CCC", "X6/ccc/patch.diff"),
                       ("Neuron", "X6/neuron/patch.diff")):
        v = line_count.count(EXP / path)
        r = rec[name]
        check("X6", f"{name}: files changed, lines added, removed, code lines added (from the diff)",
              [r["files_changed"], r["lines_added"], r["lines_removed"], r["code_lines_added"]],
              [v["files"], v["added"], v["removed"], v["code"]])
    v = line_count.count(EXP / "XRT" / "ckb-cli-creation.diff")
    check("XRT-4", "ckb-cli creation (tx sigsheet-new): lines added, code lines", [91, 87], [v["added"], v["code"]])


BENCHES = {"x1": bench_x1, "x2": bench_x2, "x3": bench_x3, "x3a": bench_x3a, "x4": bench_x4, "x7": bench_x7,
           "x2a": bench_x2a, "xc4": bench_xc4, "xrt2": bench_xrt2, "xrtb2": bench_xrtb2, "x6": bench_x6}


def fmt(v):
    s = v if isinstance(v, str) else json.dumps(v, sort_keys=True)
    return s if len(s) <= 60 else s[:57] + "..."


def main():
    ap = argparse.ArgumentParser(description="Re-run the offline design-stage benchmarks.")
    ap.add_argument("--full", action="store_true", help="X3 with the recorded trial counts (200 per case and format; slow)")
    ap.add_argument("--only", default="", help="comma-separated: " + ",".join(BENCHES))
    ap.add_argument("--out", default=str(ROOT / "bench" / "out"), help="output folder (default bench/out)")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    names = [n for n in a.only.split(",") if n] or list(BENCHES)
    t0 = time.time()
    print(f"Sigsheet design-stage benchmarks; Python {platform.python_version()}; mainnet inputs: "
          f"{'present' if have_mainnet() else 'absent (their benchmarks are skipped)'}", flush=True)
    for n in names:
        t1 = time.time()
        print(f"- {n} ...", flush=True)
        try:
            BENCHES[n](out, a.full)
        except Exception as e:  # noqa: BLE001
            row(n.upper(), "run", "-", f"{type(e).__name__}: {e}"[:300], "FAIL")
        print(f"  {n}: {time.time() - t1:.1f} s", flush=True)
    counts = {s: sum(1 for r in ROWS if r["status"].split(":")[0] == s) for s in ("PASS", "FAIL", "INFO", "SKIP")}
    lines = ["# Benchmark run", "",
             f"Run on {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}; Python {platform.python_version()} on "
             f"{platform.system()} {platform.machine()}; {time.time() - t0:.0f} s; "
             f"{'full' if a.full else 'default'} run; mainnet inputs {'present' if have_mainnet() else 'absent'}.", "",
             "Recorded values are the design-stage measurements in experiments/*/results/ (throwaway prototypes and "
             "patched copies of the wallets). Times are this machine's, for reference only.", "",
             f"PASS {counts['PASS']}, FAIL {counts['FAIL']}, INFO {counts['INFO']}, SKIP {counts['SKIP']}", "",
             "| Benchmark | Measure | Recorded (design-stage) | Measured | Status |", "|---|---|---|---|---|"]
    for r in ROWS:
        cells = [r["benchmark"], r["measure"], fmt(r["recorded"]), fmt(r["measured"]), r["status"]]
        lines.append("| " + " | ".join(str(x).replace("|", "/") for x in cells) + " |")
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    (out / "summary.json").write_text(json.dumps({"counts": counts, "rows": ROWS}, indent=1, default=str))
    w = [10, 62, 26, 26]
    print()
    print(f"{'Benchmark':<{w[0]}} {'Measure':<{w[1]}} {'Recorded':<{w[2]}} {'Measured':<{w[3]}} Status")
    for r in ROWS:
        meas = r["measure"] if len(r["measure"]) <= w[1] else r["measure"][:w[1] - 3] + "..."
        print(f"{r['benchmark']:<{w[0]}} {meas:<{w[1]}} {fmt(r['recorded'])[:w[2]]:<{w[2]}} "
              f"{fmt(r['measured'])[:w[3]]:<{w[3]}} {r['status']}")
    print(f"\nPASS {counts['PASS']}, FAIL {counts['FAIL']}, INFO {counts['INFO']}, SKIP {counts['SKIP']}. "
          f"Full table: {out / 'summary.md'}")
    sys.exit(1 if counts["FAIL"] else 0)


if __name__ == "__main__":
    main()
