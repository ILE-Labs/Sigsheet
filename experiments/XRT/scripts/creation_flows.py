#!/usr/bin/env python3
"""XRT-4: two wallets create the Sigsheet file themselves, on the devnet, with no prototype in the flow.

  C1. ckb-cli creates: its own `tx init`, `add-multisig-config`, `add-input`, `add-output` build the unsigned
      transaction (ckb-cli's `tx` file), then the new `tx sigsheet-new` writes the Sigsheet file (fetching each
      input's previous transaction from the node). CCC signs, ckb-cli signs, ckb-cli sends.
  C2. CCC creates (XRT/ccc-create, on X6's patched CCC): CCC builds the transaction and writes the file. ckb-cli
      signs, CCC signs, CCC finalizes and sends.
  C3. Cross-check: CCC creates a file for ckb-cli's exact transaction from C1; the two files are compared byte for
      byte.
Every file is also read by the prototype's strict reader (it accepts, or the flow stops).
Fresh test keys (keys/xrt/): members x0, x1, x2 of a v2 2-of-3. ckb-cli: XRT's copy of X6's patch plus creation
(`ckb-cli-src`, its own build). CCC: X6's harness and patched core, unchanged, plus XRT/ccc-create.

Run from experiments/XRT/ with the devnet running:  python3 -I -X utf8 scripts/creation_flows.py > results/creation.json
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
EXP = HERE.parent
INV = EXP.parent
sys.path.insert(0, str(EXP / "prototypes"))
import core  # noqa: E402
import devnet  # noqa: E402
import fmt_c  # noqa: E402
from core import c  # noqa: E402

CKBCLI = HERE / "ckb-cli-src" / "target" / "debug" / "ckb-cli"
# ckb-cli v2.0.0 as released (the same commit, 80efc21), for building the `tx` file with ckb-cli's own commands: the
# debug build of `tx add-output` panics on clap's debug-only argument check (upstream code, not the patch).
CKBCLI_RELEASE = pathlib.Path.home() / ".ckbup" / "bin" / "ckb-cli"
CKBCLI_HOME = INV / "keys" / "ckb-cli-home-s4"
CCC_HARNESS = EXP / "X6" / "ccc" / "harness"
TSX = CCC_HARNESS / "node_modules" / ".bin" / "tsx"
KEYS = json.loads((INV / "keys" / "xrt" / "keys.json").read_text())
OUT = HERE / "results" / "creation"
ENV = {**os.environ, "CKB_CLI_HOME": str(CKBCLI_HOME), "TMPDIR": str(HERE / "scratch.tmp")}
CAP = 300 * devnet.CKB


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def keys_outside_checkout(path):
    """Test keys must never be written inside this repository: `keys` at its root must be a link to a folder
    outside it (for example `ln -s "$(mktemp -d)" keys`), which git ignores."""
    root = pathlib.Path(__file__).resolve().parents[3]
    p = pathlib.Path(path).resolve()
    if p == root or root in p.parents:
        raise SystemExit(f"refusing to write a key inside the checkout ({p}); make keys a link to a folder outside "
                         "it: ln -s \"$(mktemp -d)\" keys")
    return path


def privkey(i):
    f = keys_outside_checkout(INV / "keys" / "xrt" / f"x{i}.privkey")
    if not f.exists():
        f.write_text(KEYS[i]["secret"][2:] + "\n")
        os.chmod(f, 0o600)
    return f


def run(args, cwd=None):
    t0 = time.time()
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=ENV)
    return {"cmd": " ".join(str(a) for a in args[:4]) + " ...", "exit": p.returncode, "seconds": round(time.time() - t0, 2),
            "stdout": p.stdout.strip()[-400:], "stderr": p.stderr.strip()[-400:]}


def ckbcli(*a):
    return run([str(CKBCLI), "--url", devnet.RPC, *a])


def ckbcli_release(*a):
    return run([str(CKBCLI_RELEASE), "--url", devnet.RPC, *a])


def ccc(*a):
    return run([str(TSX), *a], cwd=CCC_HARNESS)


def strict(path):
    fmt_c.decode(pathlib.Path(path).read_bytes())
    return "accepted"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lock, cfg = devnet.multisig_lock("v2", 0, 2, [KEYS[i]["blake160"] for i in range(3)])
    fund_hash, _ = devnet.fund([{"capacity": hex(CAP), "lock": lock, "type": None}] * 2)
    k0 = devnet.KEYS["k0"]["blake160"]
    to_addr = c.address(devnet.sighash_lock(k0), "ckt")
    member_addrs = [c.address(devnet.sighash_lock(KEYS[i]["blake160"]), "ckt") for i in range(3)]
    report = {"funding_tx": fund_hash, "lock_args": lock["args"]}

    # ---- C1: ckb-cli creates
    t = OUT / "c1-ckbcli-tx.json"
    s0, s1, s2 = OUT / "c1-0-created-by-ckb-cli.json", OUT / "c1-1-ccc-x0.json", OUT / "c1-2-ckb-cli-x1.json"
    steps = [
        ckbcli_release("tx", "init", "--tx-file", str(t)),
        ckbcli_release("tx", "add-multisig-config", "--sighash-address", *member_addrs, "--require-first-n", "0",
               "--threshold", "2", "--multisig-code-hash", devnet.CODE["v2"][0], "--tx-file", str(t)),
        ckbcli_release("tx", "add-input", "--tx-hash", fund_hash, "--index", "0", "--tx-file", str(t)),
        ckbcli_release("tx", "add-output", "--to-sighash-address", to_addr, "--capacity", str((CAP - devnet.FEE) / devnet.CKB),
               "--tx-file", str(t)),
        ckbcli("tx", "sigsheet-new", "--tx-file", str(t), "--output", str(s0)),
    ]
    c1 = {"build_and_create": steps}
    if s0.exists():
        c1["created_file"] = {"bytes": s0.stat().st_size, "sha256": sha(s0), "strict_reader": strict(s0)}
        c1["ccc_sign_x0"] = ccc("sigsheet-ccc.ts", "sign", str(s0), str(s1), KEYS[0]["secret"], "devnet")
        c1["ckbcli_sign_x1"] = ckbcli("tx", "sigsheet-sign", "--sigsheet", str(s1), "--privkey-path", str(privkey(1)),
                                      "--output", str(s2))
        c1["strict_reader_on_signed"] = strict(s2)
        sent = ckbcli("tx", "sigsheet-send", "--sigsheet", str(s2))
        c1["ckbcli_send"] = sent
        try:
            h = json.loads(sent["stdout"]) if sent["stdout"].startswith('"') else sent["stdout"].strip().strip('"')
        except json.JSONDecodeError:
            h = sent["stdout"].strip().strip('"')
        if isinstance(h, str) and h.startswith("0x"):
            devnet.wait_committed(h)
            c1["committed"] = h
    report["C1_ckb_cli_creates"] = c1

    # ---- C3: CCC creates for ckb-cli's exact transaction
    if t.exists() and s0.exists():
        tx = json.loads(t.read_text())["transaction"]
        spec = {"inputs": [{"txHash": i["previous_output"]["tx_hash"], "index": i["previous_output"]["index"]} for i in tx["inputs"]],
                "outputs": [{"capacity": o["capacity"], "lock": {"codeHash": o["lock"]["code_hash"], "hashType": o["lock"]["hash_type"], "args": o["lock"]["args"]}} for o in tx["outputs"]],
                "cellDeps": [{"outPoint": {"txHash": d["out_point"]["tx_hash"], "index": d["out_point"]["index"]}, "depType": "depGroup" if d["dep_type"] == "dep_group" else "code"} for d in tx["cell_deps"]],
                "configs": [{"public_key_hashes": cfg["keys"], "require_first_n": cfg["r"], "threshold": cfg["m"]}]}
        spec_f = OUT / "c3-spec.json"
        spec_f.write_text(json.dumps(spec))
        c3_out = OUT / "c3-created-by-ccc.json"
        r = ccc(str(HERE / "ccc-create" / "run.ts"), "create", str(spec_f), str(c3_out), devnet.RPC, "devnet")
        report["C3_same_transaction"] = {"ccc_create": r, "byte_identical_to_ckb_cli_file": c3_out.exists() and c3_out.read_bytes() == s0.read_bytes()}

    # ---- C2: CCC creates (input 1 of the funding transaction)
    spec = {"inputs": [{"txHash": fund_hash, "index": "0x1"}],
            "outputs": [{"capacity": hex(CAP - devnet.FEE), "lock": {"codeHash": core.SIGHASH[0], "hashType": "type", "args": k0}}],
            "cellDeps": [{"outPoint": {"txHash": devnet.DEP_TX, "index": hex(devnet.DEP_INDEX["v2"])}, "depType": "depGroup"}],
            "configs": [{"public_key_hashes": cfg["keys"], "require_first_n": cfg["r"], "threshold": cfg["m"]}]}
    spec_f = OUT / "c2-spec.json"
    spec_f.write_text(json.dumps(spec))
    d0, d1, d2 = OUT / "c2-0-created-by-ccc.json", OUT / "c2-1-ckb-cli-x0.json", OUT / "c2-2-ccc-x2.json"
    c2 = {"ccc_create": ccc(str(HERE / "ccc-create" / "run.ts"), "create", str(spec_f), str(d0), devnet.RPC, "devnet")}
    if d0.exists():
        c2["created_file"] = {"bytes": d0.stat().st_size, "sha256": sha(d0), "strict_reader": strict(d0)}
        c2["ckbcli_sign_x0"] = ckbcli("tx", "sigsheet-sign", "--sigsheet", str(d0), "--privkey-path", str(privkey(0)), "--output", str(d1))
        c2["ccc_sign_x2"] = ccc("sigsheet-ccc.ts", "sign", str(d1), str(d2), KEYS[2]["secret"], "devnet")
        c2["strict_reader_on_signed"] = strict(d2)
        sent = ccc("sigsheet-ccc.ts", "send", str(d2), devnet.RPC, "devnet")
        c2["ccc_send"] = sent
        try:
            h = json.loads(sent["stdout"].splitlines()[-1]).get("sent")
        except (json.JSONDecodeError, IndexError, AttributeError):
            h = None
        if h:
            devnet.wait_committed(h)
            c2["committed"] = h
    report["C2_ccc_creates"] = c2
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
