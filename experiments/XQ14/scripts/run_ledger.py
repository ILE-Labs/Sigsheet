#!/usr/bin/env python3
"""XQ14: sign Sigsheet multisig transactions on the emulated Ledger (Speculos), then finish them on the devnet.

Usage, from experiments/XQ14:  python3 -I -X utf8 scripts/run_ledger.py <run name> [...]
Needs: Speculos running the app (README step 3), the devnet, and the funded cells (X5/data/funding.json).
Writes results/runs/<run>/: the Sigsheet files (C, B+w, A), the device job, the device's record (screens,
button presses, signature or error), and the outcome (signature check, devnet dry run, commit).
"""
import json
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
sys.path.insert(0, str(HERE.parent / "prototypes"))
import core  # noqa: E402
import devnet  # noqa: E402
import fmt_a  # noqa: E402
import fmt_b  # noqa: E402
import fmt_c  # noqa: E402
import job as jobs  # noqa: E402
from core import c  # noqa: E402

CKB = devnet.CKB
S6 = devnet.sighash_lock(devnet.KEYS["s6"]["blake160"])
NET = json.loads((HERE.parent / "X1" / "data" / "devnet" / "genesis-info.json").read_text())["genesis_hash"]


def lock_of(name):
    return devnet.funding()["configs"][name]["lock"]


RUNS = {
    # name: (picks, outputs, group config name, expectation)
    "genesis-member": ([("L23G", 0)], [(S6, 500 * CKB), (lock_of("L23G"), 499 * CKB)], "L23G",
                       "the device signs; with s1's signature the transaction commits"),
    "v2-member": ([("L23V", 0)], [(S6, 999 * CKB)], "L23V", "refused: the v2 lock isn't one the app knows"),
    "2024-member": ([("L23B", 0)], [(S6, 999 * CKB)], "L23B", "refused: the 2024 lock isn't one the app knows"),
    "genesis-nonmember": ([("A23G", 1)], [(S6, 999 * CKB)], "A23G",
                          "the device isn't a member: does it sign anyway?"),
    "multisig-plus-single-key": ([("L23G", 1), ("SK", 0)], [(S6, 1999 * CKB)], "L23G",
                                 "refused: a multisig input next to another input source"),
    "two-inputs-one-group": ([("L23G", 1), ("L23G", 2)], [(S6, 1999 * CKB)], "L23G",
                             "two inputs of the same multisig: one input source"),
    "v2-member-contract-data": ([("L23V", 0)], [(S6, 999 * CKB)], "L23V",
                                "with 'Allow contract data' on: does the device sign the right message for v2?",
                                {"settings": ["Allow contract data"]}),
    "v2-blind-hash": ([("L23V", 0)], [(S6, 999 * CKB)], "L23V",
                      "with 'Allow sign hash' on: the v2 lock message signed through INS_SIGN_MESSAGE_HASH",
                      {"settings": ["Allow sign hash"], "kind": "message_hash"}),
    "six-outputs": ([("L23G", 1)], [(devnet.sighash_lock(devnet.KEYS[f"s{i}"]["blake160"]), 150 * CKB)
                                    for i in range(6)] + [(lock_of("L23G"), 99 * CKB)], "L23G",
                    "refused: more than five non-change outputs"),
}


INV = HERE.parent.parent
APP = HERE / "bin" / "nervos-0.6.3-8c50034-nanos2.elf"
LOG = {"file": None}


def port_open(port):
    import socket
    with socket.socket() as so:
        so.settimeout(0.5)
        return so.connect_ex(("127.0.0.1", port)) == 0


def speculos_start(tag):
    """(Re)start Speculos in the tmux window xq14-speculos, with the default seed; log to results/speculos/."""
    subprocess.run(["tmux", "kill-window", "-t", "sigsheet:xq14-speculos"], capture_output=True)
    for _ in range(50):
        if not port_open(9999):
            break
        time.sleep(0.2)
    logdir = HERE / "results" / "speculos"
    logdir.mkdir(parents=True, exist_ok=True)
    LOG["file"] = logdir / f"{tag}.log"
    cmd = (f"PATH={INV}/refs/_ledger/bin:$PATH {INV}/refs/_ledger/venv/bin/speculos --model nanosp "
           f"--display headless --apdu-port 9999 --api-port 5000 {APP} > {LOG['file']} 2>&1")
    subprocess.run(["tmux", "new-window", "-d", "-t", "sigsheet", "-n", "xq14-speculos", cmd], check=True)
    for _ in range(100):
        if port_open(9999) and port_open(5000):
            time.sleep(1.0)
            return
        time.sleep(0.2)
    raise RuntimeError("Speculos didn't start")


def speculos_tail():
    text = LOG["file"].read_text(errors="replace") if LOG["file"] else ""
    lines = [l for l in text.splitlines() if not l.startswith("apdu: ")]
    return {"app_exited": "exit called" in text, "exit_line": [l for l in lines if "exit called" in l][-1:],
            "still_listening": port_open(9999)}


API = "http://127.0.0.1:5000"


def api_screen():
    import urllib.request
    with urllib.request.urlopen(f"{API}/events?currentscreenonly=true", timeout=10) as r:
        return " | ".join(e["text"] for e in json.loads(r.read())["events"])


def api_press(button):
    import urllib.request
    req = urllib.request.Request(f"{API}/button/{button}", data=json.dumps({"action": "press-and-release"}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=10).read()
    time.sleep(0.3)


def toggle_settings(names):
    """From the idle screen: Configuration -> each named setting -> both (toggle) -> Main menu. Returns the
    screens seen, ending with each setting's new value."""
    seen = []
    for _ in range(20):
        if api_screen().startswith("Nervos"):
            break
        time.sleep(0.2)
    api_press("right")
    seen.append(api_screen())
    api_press("both")                      # enter Configuration
    for name in names:
        for _ in range(8):
            sc = api_screen()
            if sc.startswith(name):
                break
            api_press("right")
        api_press("both")                  # toggle
        for _ in range(8):
            sc = api_screen()
            if sc.startswith(name):
                break
            api_press("right")
        seen.append(api_screen())
    for _ in range(8):
        if api_screen().startswith("Main menu"):
            break
        api_press("right")
    api_press("both")
    seen.append(api_screen())
    return seen


def node(*args, timeout=900):
    p = subprocess.run(["node", *args], cwd=HERE / "client", capture_output=True, text=True, timeout=timeout)
    return p.stdout.strip(), p.stderr.strip()


def run(name, reject=False):
    picks, outputs, cfg_name, expect = RUNS[name][:4]
    opts = RUNS[name][4] if len(RUNS[name]) > 4 else {}
    out_dir = HERE / "results" / "runs" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    model = devnet.spend_model(picks, outputs)
    gh = devnet.group_of(model, cfg_name)
    files = {"C": fmt_c.encode(model), "B+w": fmt_b.encode(model, NET, True), "A": fmt_a.encode(model)}
    (out_dir / "sigsheet-c.json").write_bytes(files["C"])
    (out_dir / "sigsheet-bw.json").write_bytes(files["B+w"])
    (out_dir / "sigsheet-a.bin").write_bytes(files["A"])
    built = {f: jobs.job_from_model(jobs.model_from_file(b, f), gh) for f, b in files.items()}
    same = len({json.dumps(j, sort_keys=True) for j in built.values()}) == 1
    job = built["C"]
    if opts.get("kind") == "message_hash":
        job = {"kind": "message_hash", "signPath": jobs.SIGN_PATH, "hash": c.b2h(jobs.message(model, gh))}
    (out_dir / "job.json").write_text(json.dumps(job, indent=1))
    speculos_start(name)
    settings_seen = toggle_settings(opts["settings"]) if opts.get("settings") else []
    stdout, stderr = node("sign.js", str(out_dir / "job.json"), str(out_dir / "device.json"),
                          *(["--reject"] if reject else []))
    time.sleep(0.5)
    dev = json.loads((out_dir / "device.json").read_text())
    res = {"run": name, "expectation": expect, "date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
           "same_device_job_from_C_Bw_A": same, "file_bytes": {f: len(b) for f, b in files.items()},
           "device": {k: dev.get(k) for k in ("result", "error", "status_code", "presses", "seconds",
                                               "annotated_bytes", "annotated_sha256", "apdus")},
           "screens": dev["screens"], "node_stdout": stdout, "node_stderr": stderr[-500:],
           "emulator": speculos_tail(), "speculos_log": str(LOG["file"].relative_to(HERE)),
           "settings_changed": settings_seen}
    if dev.get("signature"):
        sig = c.h2b("0x" + dev["signature"])
        msg = jobs.message(model, gh)
        who = core.signer_of(model, core.lock_groups(model)[gh], sig, msg)
        res["signature_recovers_to"] = who
        try:
            res["recovered_key"] = c.b2h(c.blake160(c.recover(msg, sig)))
        except ValueError as e:
            res["recovered_key"] = f"recovery failed: {e}"
        res["device_key"] = devnet.ledger_key_hash()
        res["signature_valid_for_the_lock_message"] = res["recovered_key"] == devnet.ledger_key_hash()
        if who:
            core.add_sig(model.sigs, gh, who, sig)
            core.sign_group(model, gh, devnet.secret("s1"))   # the second member: the prototype's own signer
            (out_dir / "sigsheet-c-signed.json").write_bytes(fmt_c.encode(model))
            final = core.finalize(model)
            res["lock_rules_python"] = core.lock_rule_check(final, model.prevs)
            dry = devnet.try_rpc("test_tx_pool_accept", [final, "passthrough"])
            res["devnet_dry_run"] = dry
            if dry["ok"]:
                h = devnet.rpc("send_transaction", [final, "passthrough"])
                devnet.wait_committed(h)
                res["committed_tx"] = h
                res["committed_block"] = int(devnet.rpc("get_transaction", [h])["tx_status"]["block_number"], 16)
    (out_dir / "result.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res.get(k) for k in ("run", "same_device_job_from_C_Bw_A", "signature_valid_for_the_lock_message",
                                              "committed_tx", "committed_block")} | {"device": res["device"]}))
    return res


if __name__ == "__main__":
    for n in sys.argv[1:]:
        run(n)


def run_case_file(name, case_file, settings=()):
    """Send a real case's lock group (from X2's case models) to the device: refusals and screens only (the
    emulator's key isn't a member, and mainnet transactions are never sent anywhere)."""
    d = json.loads((HERE.parent / "X2" / "cases" / case_file).read_text())
    m = d["model"]
    model = core.Model(m["tx"], m["prevs"], m["configs"], {})
    gh = [g for g, x in core.lock_groups(model).items() if x["kind"] == "multisig"][0]
    out_dir = HERE / "results" / "runs" / name
    out_dir.mkdir(parents=True, exist_ok=True)
    job = jobs.job_from_model(model, gh)
    (out_dir / "job.json").write_text(json.dumps(job))
    speculos_start(name)
    seen = toggle_settings(list(settings)) if settings else []
    stdout, stderr = node("sign.js", str(out_dir / "job.json"), str(out_dir / "device.json"), timeout=3600)
    time.sleep(0.5)
    dev = json.loads((out_dir / "device.json").read_text())
    res = {"run": name, "case": case_file, "settings_changed": seen,
           "device": {k: dev.get(k) for k in ("result", "error", "presses", "seconds", "annotated_bytes", "apdus")},
           "screens": dev["screens"], "emulator": speculos_tail(), "speculos_log": str(LOG["file"].relative_to(HERE))}
    if dev.get("signature"):
        msg = jobs.message(model, gh)
        res["recovered_key"] = c.b2h(c.blake160(c.recover(msg, c.h2b("0x" + dev["signature"]))))
        res["device_key"] = devnet.ledger_key_hash()
    (out_dir / "result.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("run", "device", "emulator")}))
    return res
