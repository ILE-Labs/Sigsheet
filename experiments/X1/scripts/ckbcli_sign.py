#!/usr/bin/env python3
"""X1, ckb-cli itself: sign every synthetic case with the installed ckb-cli 2.0.0 (80efc21), through its `tx` file.

Usage, from experiments/X1:  python3 -I -X utf8 scripts/ckbcli_sign.py [case id ...]
With case ids, only those cases are (re)signed and merged into results/ckb-cli.json; the others keep
their earlier results (a case whose inputs are already spent can't be signed again).
For each devnet case, writes results/ckb-cli/<case>.json in ckb-cli's own `tx` file format
(ReprTxHelper: transaction, multisig_configs, signatures), then runs, for each designated signer:
    ckb-cli --url http://127.0.0.1:8114/ tx sign-inputs --tx-file <file> --privkey-path <key> --output-format json
and records the signatures ckb-cli prints, or its error. CKB_CLI_HOME points inside keys/, so
nothing is written to ~/.ckb-cli. ckb-cli reads the input cells from the devnet node (live cells).
"""
import json
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ckbcore as c  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
KEYDIR = (HERE / "../../keys/x1").resolve()
KEYS = {k["name"]: k for k in json.loads((KEYDIR / "keys.json").read_text())}
ENV = dict(os.environ, CKB_CLI_HOME=str((HERE / "../../keys/ckb-cli-home").resolve()))
URL = "http://127.0.0.1:8114/"
CODE_FOR_CKBCLI = {"genesis": "0x5c5069eb0857efc65e1bca0c07df34c31663b3622fd3876c876320fc9634e2a8",
                   "v2": "0x36c971b8d41fbd94aabca77dc75e826729ac98447b46f91e00796155dddb0d29",
                   # ckb-cli has no code hash for the 2024 deployment; the file names the genesis one,
                   # and ckb-cli decides by the input's real lock (it skips unknown code hashes).
                   "2024": "0x5c5069eb0857efc65e1bca0c07df34c31663b3622fd3876c876320fc9634e2a8"}


def tx_file(case):
    cfgs = {}
    for g in case["groups"]:
        if g["kind"] != "multisig":
            continue
        script_hash = c.b2h(c.blake160(c.h2b(g["script"])))
        cfgs[script_hash] = {
            "lock_code_hash": CODE_FOR_CKBCLI[g["deployment"]],
            "sighash_addresses": [KEYS[m]["address"] for m in g["members"]],
            "require_first_n": g["multisig"]["require_first_n"],
            "threshold": g["multisig"]["threshold"],
        }
    return {"transaction": case["tx"], "multisig_configs": cfgs, "signatures": {}}


def main():
    out_dir = HERE / "results" / "ckb-cli"
    out_dir.mkdir(parents=True, exist_ok=True)
    prev = HERE / "results" / "ckb-cli.json"
    only = set(sys.argv[1:])
    summary = json.loads(prev.read_text()) if (prev.exists() and only) else {"tool": "ckb-cli 2.0.0 (80efc21), tx sign-inputs", "cases": {}}
    for f in sorted((HERE / "cases").glob("S*.json")):
        case = json.loads(f.read_text())
        if only and case["id"] not in only:
            continue
        path = out_dir / f"{case['id']}.json"
        path.write_text(json.dumps(tx_file(case), indent=1))
        signers = sorted({k for g in case["groups"] for k in g.get("signers", [])})
        res = summary["cases"][case["id"]] = {}
        for k in signers:
            cmd = ["ckb-cli", "--url", URL, "tx", "sign-inputs", "--tx-file", str(path),
                   "--privkey-path", str(KEYDIR / f"{k}.privkey"), "--output-format", "json"]
            p = subprocess.run(cmd, capture_output=True, text=True, env=ENV, timeout=120)
            entry = {"command": " ".join(cmd[:1] + cmd[1:]).replace(str(KEYDIR), "<keys/x1>"),
                     "exit": p.returncode}
            try:
                entry["output"] = json.loads(p.stdout)
            except json.JSONDecodeError:
                entry["stdout"] = p.stdout[-800:]
                entry["stderr"] = p.stderr[-800:]
            res[k] = entry
            print(case["id"], k, p.returncode, (p.stdout.strip() or p.stderr.strip())[:200].replace("\n", " "))
    (HERE / "results" / "ckb-cli.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
