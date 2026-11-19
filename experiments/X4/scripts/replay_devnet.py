#!/usr/bin/env python3
"""X4 part 3: replay on the devnet. Send again a transaction that X5 committed (its inputs are now spent), and send
its signatures on a different transaction spending a fresh cell of the same multisig.

Usage, from experiments/X4:  python3 -I -X utf8 scripts/replay_devnet.py > results/replay-devnet.json
"""
import json
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import core  # noqa: E402
import devnet  # noqa: E402
from core import c  # noqa: E402

out = {"date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
f1 = json.loads((HERE.parent / "X5" / "results" / "x5-f1.json").read_text())["flows"]["F1-pass-along-2of3-v2"]
h = [s for s in f1 if s.get("committed_tx")][0]["committed_tx"]
tx = devnet.get_tx(h)
tx = {k: tx[k] for k in core.RAW_FIELDS + ("witnesses",)}
out["resend_committed_tx"] = {"tx": h, "result": devnet.try_rpc("send_transaction", [tx, "passthrough"])}
# Same multisig (A23V), a fresh cell, same outputs: the old witness (signatures) on the new transaction.
fresh = devnet.spend_model([("A23V", 6)], [(devnet.sighash_lock(devnet.KEYS["s6"]["blake160"]), 999 * devnet.CKB)])
moved = dict(fresh.tx)
moved["witnesses"] = list(tx["witnesses"])
out["old_signatures_on_new_tx"] = {"dry_run": devnet.try_rpc("test_tx_pool_accept", [moved, "passthrough"]),
                                   "python_lock_rules": core.lock_rule_check(moved, fresh.prevs)}
print(json.dumps(out, indent=1))
