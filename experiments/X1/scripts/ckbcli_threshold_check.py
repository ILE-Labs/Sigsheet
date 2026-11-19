#!/usr/bin/env python3
"""X1 side check: what ckb-cli 2.0.0 does with more than M signatures, then with exactly M.

Usage, from experiments/X1:  python3 -I -X utf8 scripts/ckbcli_threshold_check.py
Uses case S4N (v2, R=1, M=2, N=3: k4 required, k1, k2), whose input cell is still live because S4N was
only a negative dry run. Steps, all through ckb-cli's own `tx` file and commands:
1. sign with k4 using `tx sign-inputs`;
2. add three signatures (k4, k1, k2) with `tx add-signature`, then `tx send`: ckb-cli must refuse;
3. a fresh file with k4 and k2 only, then `tx send`: must be accepted and committed.
Writes results/ckbcli-threshold-check.json.
"""
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent.parent
KEYDIR = (HERE / "../../keys/x1").resolve()
ENV = dict(os.environ, CKB_CLI_HOME=str((HERE / "../../keys/ckb-cli-home").resolve()))
URL = "http://127.0.0.1:8114/"
CASE = "S4N-v2-first-R-missing-required"


def run(args):
    p = subprocess.run(["ckb-cli", "--url", URL, *args], capture_output=True, text=True, env=ENV, timeout=120)
    return {"command": "ckb-cli --url " + URL + " " + " ".join(args).replace(str(KEYDIR), "<keys/x1>"),
            "exit": p.returncode, "out": (p.stdout + p.stderr).strip()[-600:]}


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read()).get("result")


def main():
    case = json.loads((HERE / "cases" / f"{CASE}.json").read_text())
    lock_arg = case["groups"][0]["lock"]["args"]
    base = json.loads((HERE / "results" / "ckb-cli" / f"{CASE}.json").read_text())
    base["signatures"] = {}
    sigs = {}
    cli = json.loads((HERE / "results" / "ckb-cli.json").read_text())["cases"][CASE]
    for k in ("k1", "k2"):
        sigs[k] = cli[k]["output"][0]["signature"]
    log = []
    tmp = HERE / "results" / "ckb-cli" / f"{CASE}-threshold.json"
    tmp.write_text(json.dumps(base, indent=1))
    r = run(["tx", "sign-inputs", "--tx-file", str(tmp), "--privkey-path", str(KEYDIR / "k4.privkey"), "--output-format", "json"])
    log.append(r)
    sigs["k4"] = json.loads(r["out"][r["out"].index("["):])[0]["signature"]
    for k in ("k4", "k1", "k2"):
        log.append(run(["tx", "add-signature", "--tx-file", str(tmp), "--lock-arg", lock_arg, "--signature", sigs[k]]))
    over = run(["tx", "send", "--tx-file", str(tmp)])
    log.append(over)
    ok_file = HERE / "results" / "ckb-cli" / f"{CASE}-exact.json"
    ok_file.write_text(json.dumps(base, indent=1))
    for k in ("k4", "k2"):
        log.append(run(["tx", "add-signature", "--tx-file", str(ok_file), "--lock-arg", lock_arg, "--signature", sigs[k]]))
    exact = run(["tx", "send", "--tx-file", str(ok_file)])
    log.append(exact)
    h = case["tx_hash"]
    blk = None
    for _ in range(60):
        st = rpc("get_transaction", [h])
        if st and st["tx_status"]["status"] == "committed":
            blk = int(st["tx_status"]["block_number"], 16)
            break
        time.sleep(1)
    out = {"case": CASE, "three_signatures_refused": over["exit"] != 0, "three_signatures_message": over["out"],
           "exact_two_sent": exact["exit"] == 0, "tx_hash": h, "committed_block": blk, "log": log}
    (HERE / "results" / "ckbcli-threshold-check.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "log"}, indent=1))


if __name__ == "__main__":
    main()
