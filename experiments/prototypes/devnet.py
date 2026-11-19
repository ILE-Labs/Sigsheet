"""Devnet helpers for the experiments X3, X4, X5 and XQ14: RPC, funding from the miner key, sending.

The local devnet is X1's (`devnet/node`, ckb 0.210.0; genesis holds all three multisig deployments). Keys:
X1's k0 (the miner's key, which holds the block rewards) pays for funding; the multisig members are fresh
test keys s0-s7 (`keys/s4/keys.json`, made with X1's keygen.py; never stored in this repository); the Ledger emulator's key is
Speculos's default test seed at m/44'/309'/0'/0/0 (XQ14 `results/pubkey-path0.json`).
"""
import json
import pathlib
import time
import urllib.request

import core
from core import c

HERE = pathlib.Path(__file__).resolve().parent
INV = HERE.parent.parent
RPC = "http://127.0.0.1:8114/"
def _load_keys(path):
    """Test keys made by X1's keygen.py; none when the file doesn't exist (offline use, as in bench/)."""
    return {k["name"]: k for k in json.loads(path.read_text())} if path.exists() else {}


X1_KEYS = _load_keys(INV / "keys" / "x1" / "keys.json")
S4_KEYS = _load_keys(INV / "keys" / "s4" / "keys.json")
KEYS = {**X1_KEYS, **S4_KEYS}
GEN = json.loads((HERE.parent / "X1" / "data" / "devnet" / "genesis-info.json").read_text())
LEDGER_FILE = HERE.parent / "XQ14" / "results" / "pubkey-path0.json"
CKB = 100_000_000
FEE = 100_000

DEP_TX = [x for x in GEN["cells"] if x["dep_group_lists"]][0]["out_point"].split(":")[0]
DEP_INDEX = {"sighash": 0, "genesis": 1, "2024": 2, "v2": 3}
CODE = {
    "genesis": ("0x5c5069eb0857efc65e1bca0c07df34c31663b3622fd3876c876320fc9634e2a8", "type"),
    "2024": (GEN["multisig"]["2024"]["devnet_type_hash"], "type"),
    "v2": ("0x36c971b8d41fbd94aabca77dc75e826729ac98447b46f91e00796155dddb0d29", "data1"),
}


def ledger_key_hash():
    d = json.loads(LEDGER_FILE.read_text())
    return "0x" + d["lockArg"]


def rpc(method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(f"{method}: {out['error']}")
    return out["result"]


def try_rpc(method, params):
    try:
        return {"ok": True, "result": rpc(method, params)}
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}


def wait_committed(h, timeout=180):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = rpc("get_transaction", [h])
        if r and r["tx_status"]["status"] == "committed":
            return r["tx_status"]["block_hash"]
        time.sleep(1)
    raise RuntimeError(f"{h} not committed after {timeout} s")


def cell_dep(name):
    return {"out_point": {"tx_hash": DEP_TX, "index": hex(DEP_INDEX[name])}, "dep_type": "dep_group"}


def sighash_lock(key_hash):
    return {"code_hash": core.SIGHASH[0], "hash_type": "type", "args": key_hash}


def multisig_lock(deployment, r, m, key_hashes, since=None):
    cfg = {"r": r, "m": m, "keys": list(key_hashes)}
    args = c.h2b(core.config_id(cfg)) + (c.u64(since) if since is not None else b"")
    code_hash, hash_type = CODE[deployment]
    return {"code_hash": code_hash, "hash_type": hash_type, "args": c.b2h(args)}, cfg


def mature_cells(key_hash, need, limit=50):
    """Live cells of a sighash key, oldest first, skipping cellbase outputs younger than 4 epochs (tx index 0)."""
    tip = int(rpc("get_tip_block_number", []), 16)
    res = rpc("get_cells", [{"script": sighash_lock(key_hash), "script_type": "lock",
                             "filter": {"output_data_len_range": ["0x0", "0x1"]}}, "asc", hex(limit)])
    picked, total = [], 0
    for cell in res["objects"]:
        if cell["output"]["type"] is not None:
            continue
        if int(cell["block_number"], 16) > tip - 4000:  # well past cellbase maturity on this devnet
            continue
        picked.append(cell)
        total += int(cell["output"]["capacity"], 16)
        if total >= need:
            return picked, total
    raise RuntimeError("not enough mature capacity")


def sign_sighash_inputs(tx, secret_hex, input_indices):
    """Sign one single-key lock group (all given inputs share the lock) in place."""
    w = [c.h2b(x) for x in tx["witnesses"]]
    zeroed = c.witness_args(bytes(65))
    w[input_indices[0]] = zeroed
    msg = c.sighash_all_message(tx, input_indices, w, zeroed)
    w[input_indices[0]] = c.witness_args(c.sign(msg, c.h2b(secret_hex)))
    tx["witnesses"] = [c.b2h(x) for x in w]


def fund(outputs, outputs_data=None, payer="k0"):
    """One transaction from the payer's mature cells creating the given outputs; returns its hash and the tx."""
    key = KEYS[payer]
    need = sum(int(o["capacity"], 16) for o in outputs) + FEE + 62 * CKB
    cells, total = mature_cells(key["blake160"], need)
    change = total - sum(int(o["capacity"], 16) for o in outputs) - FEE
    outs = outputs + [{"capacity": hex(change), "lock": sighash_lock(key["blake160"]), "type": None}]
    data = (outputs_data or ["0x"] * len(outputs)) + ["0x"]
    tx = {"version": "0x0", "cell_deps": [cell_dep("sighash")], "header_deps": [],
          "inputs": [{"since": "0x0", "previous_output": x["out_point"]} for x in cells],
          "outputs": outs, "outputs_data": data, "witnesses": ["0x"] * len(cells)}
    sign_sighash_inputs(tx, key["secret"], list(range(len(cells))))
    h = rpc("send_transaction", [tx, "passthrough"])
    wait_committed(h)
    return h, tx


def get_tx(h):
    return rpc("get_transaction", [h])["transaction"]


# ------------------------------------------------------------------ cases from the funded cells

FUNDING_FILE = HERE.parent / "X5" / "data" / "funding.json"


def funding():
    return json.loads(FUNDING_FILE.read_text())


def spend_model(picks, outputs, extra_witnesses=(), since_for=None):
    """An unsigned Sigsheet model spending funded cells.

    picks: [(config name, cell number)] from X5/data/funding.json; outputs: [(lock, capacity in shannons)];
    extra_witnesses: hex witnesses appended after the inputs' witnesses; since_for: {config name: since value}.
    Every input's witness is a template ("0x"); cell deps are the dep groups the deployments need.
    """
    f = funding()
    since_for = since_for or {}
    inputs, deps, configs, prevs = [], [], {}, {}
    for name, n in picks:
        e = f["configs"][name]
        op = e["cells"][n]
        inputs.append({"since": hex(since_for.get(name, 0)), "previous_output": op})
        dep = e["deployment"] if e["deployment"] != "sighash" else "sighash"
        if dep not in deps:
            deps.append(dep)
        if e["config"]:
            configs[core.config_id(e["config"])] = e["config"]
        if op["tx_hash"] not in prevs:
            prevs[op["tx_hash"]] = core.raw_of(get_tx(op["tx_hash"]))
    tx = {"version": "0x0", "cell_deps": [cell_dep(d) for d in deps], "header_deps": [], "inputs": inputs,
          "outputs": [{"capacity": hex(cap), "lock": lock, "type": None} for lock, cap in outputs],
          "outputs_data": ["0x"] * len(outputs), "witnesses": ["0x"] * len(inputs) + list(extra_witnesses)}
    return core.Model(tx, prevs, configs, {})


def secret(name):
    return KEYS[name]["secret"]


def group_of(model, config_name):
    lock = funding()["configs"][config_name]["lock"]
    return c.b2h(c.script_hash(lock))
