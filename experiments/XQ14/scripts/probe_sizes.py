#!/usr/bin/env python3
"""XQ14: how large a previous transaction can the emulated Ledger take? (the 0x9405 question, neuron#3095)

Usage, from experiments/XQ14:  python3 -I -X utf8 scripts/probe_sizes.py > results/size-probes.json

Each probe spends output 0 of a synthetic previous transaction P: output 0 is the genesis 2-of-3 [L, s1, s2]
(L = the emulator's key), output 1 a single-key cell holding N bytes of data, output 2 another [L, s1, s2] cell.
The spending transaction pays 999 CKB to s6. The device hashes P itself, so P needn't exist on any chain; the
signature is checked against the lock's message computed by the prototypes from the same data. "x2" probes
spend outputs 0 and 2 of P, so P is sent twice, as hw-app-ckb pairs input i with context i (hw-app-ckb src/Ckb.js) and as
PR #34's two inputs would be. Each probe restarts Speculos (a refused transaction makes the app exit).
"""
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
import run_ledger as rl  # noqa: E402
from run_ledger import c, core, devnet, jobs  # noqa: E402

L23G = rl.lock_of("L23G")
CFG = devnet.funding()["configs"]["L23G"]["config"]
SIZES = [0, 16_000, 64_000, 128_000, 283_000, 400_000, 1_000_000]


def synthetic(n, two_inputs):
    p = {"version": "0x0", "cell_deps": [devnet.cell_dep("sighash")], "header_deps": [],
         "inputs": [{"since": "0x0", "previous_output": {"tx_hash": "0x" + "11" * 32, "index": "0x0"}}],
         "outputs": [{"capacity": hex(1000 * rl.CKB), "lock": L23G, "type": None},
                     {"capacity": hex((n + 100) * rl.CKB), "lock": rl.S6, "type": None},
                     {"capacity": hex(1000 * rl.CKB), "lock": L23G, "type": None}],
         "outputs_data": ["0x", "0x" + "ab" * n, "0x"]}
    ph = c.b2h(c.tx_hash(p))
    idx = ["0x0", "0x2"] if two_inputs else ["0x0"]
    tx = {"version": "0x0", "cell_deps": [devnet.cell_dep("genesis")], "header_deps": [],
          "inputs": [{"since": "0x0", "previous_output": {"tx_hash": ph, "index": i}} for i in idx],
          "outputs": [{"capacity": hex((999 + 1000 * (len(idx) - 1)) * rl.CKB), "lock": rl.S6, "type": None}],
          "outputs_data": ["0x"], "witnesses": ["0x"] * len(idx)}
    model = core.Model(tx, {ph: p}, {core.config_id(CFG): CFG}, {})
    return model, len(c.raw_transaction(p))


def main():
    out = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "probes": []}
    for two in (False, True):
        for n in SIZES:
            name = f"probe-{n}-{'x2' if two else 'x1'}"
            model, praw = synthetic(n, two)
            gh = c.b2h(c.script_hash(L23G))
            job = jobs.job_from_model(model, gh)
            d = HERE / "results" / "probes" / name
            d.mkdir(parents=True, exist_ok=True)
            (d / "job.json").write_text(json.dumps(job))
            rl.speculos_start(name)
            stdout, stderr = rl.node("sign.js", str(d / "job.json"), str(d / "device.json"), timeout=3600)
            time.sleep(0.5)
            dev = json.loads((d / "device.json").read_text())
            r = {"name": name, "data_bytes": n, "previous_tx_raw_bytes": praw, "inputs_from_it": 2 if two else 1,
                 "result": dev["result"], "error": dev.get("error"), "seconds": dev["seconds"],
                 "annotated_bytes": dev["annotated_bytes"], "apdus": dev["apdus"], "screens": len(dev["screens"]),
                 "presses": dev["presses"], "emulator": rl.speculos_tail()}
            if dev.get("signature"):
                msg = jobs.message(model, gh)
                r["signature_recovers_to_device_key"] = c.b2h(c.blake160(c.recover(msg, c.h2b("0x" + dev["signature"])))) \
                    == devnet.ledger_key_hash()
            out["probes"].append(r)
            print(json.dumps({k: r[k] for k in ("name", "result", "seconds", "apdus")}), file=sys.stderr)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
