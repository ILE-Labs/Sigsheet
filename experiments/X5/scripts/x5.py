#!/usr/bin/env python3
"""X5: G1 and G2 end to end on the devnet, with the patched tools signing one shared Sigsheet file (path C).

Usage, from experiments/X5:  python3 -I -X utf8 scripts/x5.py [flow ...] > results/x5.json
Needs: the devnet; the patched ckb-cli (X6, target/debug/ckb-cli), the patched CCC (X6 harness, tsx) and the
patched Neuron (X6, jest harness tests/x6/x6-sigsheet.test.ts); the funded devnet cells (data/funding.json).

Every flow starts from an unsigned file that a creator writes (here the Python prototype; any tool could), then
signers in different tools add their signatures, either passing one file along or each signing their own copy and
posting it to a shared folder (a stand-in for PR comments, a chat or a relay), and anyone merges and finalizes.
No step needs a collector: each signer works on the file it receives, and the merge gives the same bytes in any
order. Each step's file is kept (results/<flow>/NN-<step>.json) with its SHA-256; the final transaction is sent
to the devnet and its hash and block recorded.
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

CKBCLI = EXP / "X6" / "ckb-cli" / "src-copy" / "target" / "debug" / "ckb-cli"
CCC_DIR = EXP / "X6" / "ccc" / "harness"
NEURON_DIR = EXP / "X6" / "neuron" / "packages" / "neuron-wallet"
CKBCLI_HOME = INV / "keys" / "ckb-cli-home-s4"
CKB = devnet.CKB
S6 = devnet.sighash_lock(devnet.KEYS["s6"]["blake160"])


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


class Flow:
    def __init__(self, name):
        self.name = name
        self.dir = HERE / "results" / name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.steps = []
        self.n = 0

    def path(self, label):
        self.n += 1
        return self.dir / f"{self.n:02d}-{label}.json"

    def record(self, tool, action, out, extra=None):
        e = {"step": self.n, "tool": tool, "action": action, "file": str(pathlib.Path(out).relative_to(HERE)),
             "sha256": sha(out) if pathlib.Path(out).exists() else None}
        if pathlib.Path(out).exists() and out.suffix == ".json" and action != "finalize":
            try:
                m = fmt_c.decode(pathlib.Path(out).read_bytes())
                e["signed_members"] = {gh[:10]: st["signed"] for gh, st in core.status(m).items()}
            except core.SigsheetError as err:
                e["decode_error"] = str(err)
        if extra:
            e.update(extra)
        self.steps.append(e)
        return out

    # ---- tools
    def create(self, model):
        out = self.path("unsigned")
        out.write_bytes(fmt_c.encode(model))
        return self.record("python prototype", "create", out)

    def ckbcli_sign(self, src, key):
        out = self.path(f"ckb-cli-{key}")
        t0 = time.time()
        p = subprocess.run([str(CKBCLI), "--url", devnet.RPC, "tx", "sigsheet-sign", "--sigsheet", str(src),
                            "--privkey-path", str(INV / "keys" / "s4" / f"{key}.privkey"), "--output", str(out)],
                           capture_output=True, text=True, env={**os.environ, "CKB_CLI_HOME": str(CKBCLI_HOME)})
        return self.record("ckb-cli (patched)", f"sign with {key}", out,
                           {"stdout": p.stdout.strip()[-300:], "stderr": p.stderr.strip()[-300:],
                            "seconds": round(time.time() - t0, 2)})

    def ccc_sign(self, src, key):
        out = self.path(f"ccc-{key}")
        t0 = time.time()
        p = subprocess.run(["npx", "tsx", "sigsheet-ccc.ts", "sign", str(src), str(out), devnet.secret(key), "devnet"],
                           cwd=CCC_DIR, capture_output=True, text=True)
        return self.record("CCC (patched)", f"sign with {key}", out,
                           {"stdout": p.stdout.strip()[-300:], "seconds": round(time.time() - t0, 2)})

    def neuron_sign(self, src, key):
        out = self.path(f"neuron-{key}")
        t0 = time.time()
        env = {**os.environ, "ELECTRON_OVERRIDE_DIST_PATH": "/nonexistent-electron", "SIGSHEET_IN": str(src),
               "SIGSHEET_OUT": str(out), "SIGNER_SECRET": devnet.secret(key),
               "SIGNER_BLAKE160": devnet.KEYS[key]["blake160"]}
        p = subprocess.run(["../../node_modules/.bin/jest", "tests/x6/x6-sigsheet.test.ts"], cwd=NEURON_DIR,
                           capture_output=True, text=True, env=env)
        ok = "1 passed" in p.stderr
        return self.record("Neuron (patched)", f"sign with {key}", out,
                           {"jest_passed": ok, "seconds": round(time.time() - t0, 2),
                            "stderr_tail": "" if ok else p.stderr[-500:]})

    def python_sign(self, src, key):
        out = self.path(f"python-{key}")
        m = fmt_c.decode(pathlib.Path(src).read_bytes())
        for gh, g in core.lock_groups(m).items():
            try:
                core.sign_group(m, gh, devnet.secret(key))
            except core.SigsheetError:
                pass
        out.write_bytes(fmt_c.encode(m))
        return self.record("python prototype", f"sign with {key}", out)

    def ckbcli_merge(self, *srcs):
        out = self.path("ckb-cli-merge")
        args = [str(CKBCLI), "tx", "sigsheet-merge"]
        for s in srcs:
            args += ["--sigsheet", str(s)]
        p = subprocess.run(args + ["--output", str(out)], capture_output=True, text=True,
                           env={**os.environ, "CKB_CLI_HOME": str(CKBCLI_HOME)})
        return self.record("ckb-cli (patched)", f"merge {len(srcs)} files", out, {"stderr": p.stderr.strip()[-300:]})

    def ccc_merge(self, *srcs):
        out = self.path("ccc-merge")
        p = subprocess.run(["npx", "tsx", "sigsheet-ccc.ts", "merge", str(out), *map(str, srcs), "devnet"],
                           cwd=CCC_DIR, capture_output=True, text=True)
        return self.record("CCC (patched)", f"merge {len(srcs)} files", out, {"stdout": p.stdout.strip()[-200:]})

    def python_merge(self, *srcs):
        out = self.path("python-merge")
        out.write_bytes(fmt_c.encode(core.merge(*[fmt_c.decode(pathlib.Path(s).read_bytes()) for s in srcs])))
        return self.record("python prototype", f"merge {len(srcs)} files", out)

    def finalize_send(self, tool, src):
        out = self.path(f"{tool}-final-tx")
        if tool == "ckb-cli":
            p = subprocess.run([str(CKBCLI), "--url", devnet.RPC, "tx", "sigsheet-send", "--sigsheet", str(src),
                                "--output", str(out)], capture_output=True, text=True,
                               env={**os.environ, "CKB_CLI_HOME": str(CKBCLI_HOME)})
            err = p.stderr.strip()[-400:]
        elif tool == "ccc":
            p = subprocess.run(["npx", "tsx", "sigsheet-ccc.ts", "finalize", str(src), str(out), "devnet"],
                               cwd=CCC_DIR, capture_output=True, text=True)
            err = p.stderr.strip()[-400:] if p.returncode else ""
        else:
            m = fmt_c.decode(pathlib.Path(src).read_bytes())
            try:
                out.write_text(json.dumps(core.finalize(m), indent=1))
                err = ""
            except core.SigsheetError as e:
                err = str(e)
        if not out.exists():
            return self.record(tool, "finalize", out, {"error": err or "no output"})
        final = json.loads(out.read_text())
        final = {k: final[k] for k in core.RAW_FIELDS + ("witnesses",)}
        prevs = fmt_c.decode(pathlib.Path(src).read_bytes()).prevs
        rules = core.lock_rule_check(final, prevs)
        sent = devnet.try_rpc("send_transaction", [final, "passthrough"])
        extra = {"lock_rules_python": all(rules.values()), "send": sent}
        if sent["ok"]:
            devnet.wait_committed(sent["result"])
            extra["committed_tx"] = sent["result"]
            extra["block"] = int(devnet.rpc("get_transaction", [sent["result"]])["tx_status"]["block_number"], 16)
        return self.record(f"{tool}", "finalize and send", out, extra)


# ------------------------------------------------------------------ flows

def f1_pass_along_2of3_v2():
    f = Flow("F1-pass-along-2of3-v2")
    a = f.create(devnet.spend_model([("A23V", 4)], [(S6, 999 * CKB)]))
    b = f.ckbcli_sign(a, "s1")
    c_ = f.ccc_sign(b, "s2")
    f.finalize_send("ccc", c_)
    return f


def f2_parallel_3of5_v2_four_signers():
    f = Flow("F2-parallel-3of5-v2-four-signers")
    a = f.create(devnet.spend_model([("B35V", 0)], [(S6, 999 * CKB)]))
    parts = [f.ckbcli_sign(a, "s5"), f.ccc_sign(a, "s1"), f.neuron_sign(a, "s3"), f.python_sign(a, "s4")]
    m1 = f.ckbcli_merge(*parts)
    m2 = f.ccc_merge(*reversed(parts))
    m3 = f.python_merge(parts[2], parts[0], parts[3], parts[1])
    f.steps.append({"merges_identical": sha(m1) == sha(m2) == sha(m3)})
    f.finalize_send("ckb-cli", m2)
    return f


def f3_genesis_neuron_then_ckbcli():
    f = Flow("F3-genesis-2of3-neuron-then-ckb-cli")
    a = f.create(devnet.spend_model([("A23G", 3)], [(S6, 999 * CKB)]))
    b = f.neuron_sign(a, "s2")
    c_ = f.ckbcli_sign(b, "s3")
    f.finalize_send("ckb-cli", c_)
    return f


def f4_extra_witness_neuron_ccc():
    f = Flow("F4-extra-witness-v2-neuron-and-ccc")
    a = f.create(devnet.spend_model([("A23V", 0)], [(S6, 999 * CKB)], extra_witnesses=["0x01020304"]))
    b = f.neuron_sign(a, "s3")
    c_ = f.ccc_sign(b, "s1")
    f.finalize_send("ccc", c_)
    return f


def f5_multisig_plus_single_key():
    f = Flow("F5-multisig-plus-single-key")
    a = f.create(devnet.spend_model([("A23V", 5), ("SK", 0)], [(S6, 1999 * CKB)]))
    parts = [f.ckbcli_sign(a, "s4"), f.ccc_sign(a, "s1"), f.neuron_sign(a, "s2")]
    m = f.python_merge(*parts)
    f.finalize_send("ccc", m)
    return f


def f6_first_r():
    f = Flow("F6-3of5-first-member-required")
    a = f.create(devnet.spend_model([("B35VR", 1)], [(S6, 999 * CKB)]))
    parts = [f.ccc_sign(a, "s2"), f.ckbcli_sign(a, "s3"), f.neuron_sign(a, "s4")]
    m = f.ckbcli_merge(*parts)
    f.finalize_send("ckb-cli", m)          # must be refused: s1 (member 0) is required
    late = f.ckbcli_sign(m, "s1")
    f.finalize_send("ckb-cli", late)
    return f


def f7_2024_ccc_only():
    f = Flow("F7-2024-deployment-ccc")
    a = f.create(devnet.spend_model([("A23B", 1)], [(S6, 999 * CKB)]))
    b = f.ccc_sign(a, "s1")
    c_ = f.ckbcli_sign(b, "s2")                 # ckb-cli can't sign the 2024 lock: expect no signature added
    d = f.ccc_sign(c_, "s3")
    f.finalize_send("ccc", d)
    return f


FLOWS = {fn.__name__: fn for fn in (f1_pass_along_2of3_v2, f2_parallel_3of5_v2_four_signers,
                                    f3_genesis_neuron_then_ckbcli, f4_extra_witness_neuron_ccc,
                                    f5_multisig_plus_single_key, f6_first_r, f7_2024_ccc_only)}


def main():
    names = sys.argv[1:] or list(FLOWS)
    out = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "flows": {}}
    for n in names:
        f = FLOWS[n]()
        out["flows"][f.name] = f.steps
        print(f.name, [(s.get("tool"), s.get("action"), s.get("committed_tx", "")[:12]) for s in f.steps
                       if "tool" in s], file=sys.stderr)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
