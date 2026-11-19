"""XQ14: from a Sigsheet file to the arguments Neuron's ledger.ts passes to the device, for one lock group.

Neuron's `signMultisig` (transaction-sender.ts, d3a7467) hands the device: the raw transaction (RPC form), the lock
group's witnesses with the first one's lock set to the multisig script plus M x 65 zero bytes, the previous
transaction of every input in input order (`context`), the sign path, and its `defaultPath` (the account path,
m/44'/309'/0') as the change path; hw-app-ckb then pairs input i with context i (hw-app-ckb src/Ckb.js). This module builds
the same arguments from a Sigsheet file, in any of the three formats, so XQ14 can check that the device receives
the same bytes whichever format the host read. One difference from Neuron, on purpose: the witnesses beyond
the inputs are passed too, because the lock's message covers them (background.md section 1; X1 case S9).
"""
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE.parent / "prototypes"))
import core  # noqa: E402
import fmt_a  # noqa: E402
import fmt_b  # noqa: E402
import fmt_c  # noqa: E402
from core import c  # noqa: E402

NEURON_CHANGE_PATH = "44'/309'/0'"   # hd.AccountExtendedPublicKey.ckbAccountPath, Neuron's defaultPath
SIGN_PATH = "44'/309'/0'/0/0"


def job_from_model(model, group_hash, sign_path=SIGN_PATH, change_path=NEURON_CHANGE_PATH):
    g = core.lock_groups(model)[group_hash]
    it, ot = core.template_parts(model, g, strict=False)
    first = c.witness_args(core.zeroed_lock(model, g), it, ot)
    w = model.tx["witnesses"]
    witnesses = [c.b2h(first)] + [w[i] for i in g["inputs"][1:] if i < len(w)]
    witnesses += [w[i] for i in range(len(model.tx["inputs"]), len(w))]
    context = [model.prevs[i["previous_output"]["tx_hash"]] for i in model.tx["inputs"]]
    return {"kind": "transaction", "signPath": sign_path, "changePath": change_path,
            "rawTx": core.raw_of(model.tx), "witnesses": witnesses, "context": context}


def model_from_file(data: bytes, fmt: str):
    if fmt == "C":
        return fmt_c.decode(data)
    if fmt == "B+w":
        return fmt_b.decode(data)[0]
    if fmt == "A":
        return fmt_a.decode(data)
    raise ValueError(fmt)


def message(model, group_hash):
    return core.group_message(model, core.lock_groups(model)[group_hash])
