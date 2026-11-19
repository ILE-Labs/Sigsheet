"""The read-only fetch of the two mainnet cases, R1 and R2, and their check.

The repository keeps no mainnet chain data, only these cases' expected values and digests. This fetch reads public
data at pinned versions, with a generic User-Agent and nothing but read calls:
- CKB mainnet JSON-RPC (`https://mainnet.ckb.dev/` by default; `--rpc` picks another): `get_transaction` for R2, its
  previous transactions, and R1's committed transaction. Every transaction hash is recomputed.
- GitHub: fiber-scripts' deploy file `deployment/mainnet/mainnet.json` at commit 026027f, and PR #34's four signature
  comments by id. Each file's SHA-256 must equal `vectors/mainnet/inputs.sha256`.
It writes only under `vectors/mainnet/.fetched/`: the fetched files in `inputs/`, and each case rebuilt as a vector
folder. Every rebuilt file's SHA-256, the messages, the unsigned id and the final transaction hash must equal
`vectors/mainnet/<id>/expected.json`. A fetched file already there is used again when its digest or hash checks.
"""

import json
import pathlib
import re
import time
import urllib.request

from ..ckb import addresses, molecule, rpc_json, scripts
from ..ckb.hashing import blake160
from ..ckb.secp256k1 import InvalidSignature, recover
from ..sigsheet import canonical, reader
from ..sigsheet.messages import message
from ..sigsheet.schema import MultisigConfig, config_to_json
from ..vectors import cases

USER_AGENT = "Mozilla/5.0"
GITHUB_RAW = "https://raw.githubusercontent.com"
GITHUB_API = "https://api.github.com"
DEPLOY_FILE = "nervosnetwork/fiber-scripts/026027f54f6a90cb48d8cc184b230e2018bb8611/deployment/mainnet/mainnet.json"
COMMENTS = (6571892250, 6573354672, 6581601897, 6605978601)
R1 = "R1-fiber-scripts-pr34"
R2 = "R2-genesis-2of3-payment"
R1_COMMITTED = "0x4396de69818bd88b7fce64797ccec25d1294912d56846432f29fd192120992ee"
R2_COMMITTED = "0x63a7f3a52fc91c52939186ca9c1064238ccdfe498d3398f25707537f591bbaa4"
SOURCES = {
    R1: "mainnet transaction 0x4396de69818bd88b7fce64797ccec25d1294912d56846432f29fd192120992ee, replayed from "
    "fiber-scripts PR #34's deploy file at 026027f and its four signature comments",
    R2: "mainnet transaction 0x63a7f3a52fc91c52939186ca9c1064238ccdfe498d3398f25707537f591bbaa4, "
    "a genesis 2-of-3 payment",
}
# A signature pasted in a PR comment, after the lock args it is for.
COMMENT_SIGNATURE = re.compile(r"0x[0-9a-f]{40,56}:\s*(0x[0-9a-f]{130})")


class FetchError(RuntimeError):
    pass


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, */*"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _rpc(url: str, method: str, params: list):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    time.sleep(1)
    if "error" in out:
        raise FetchError(f"{method} {params}: {out['error']}")
    return out["result"]


def pinned_digests(root: pathlib.Path) -> dict[str, str]:
    out = {}
    for line in (root / "mainnet" / "inputs.sha256").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            digest, name = line.split()
            out[name] = digest
    return out


def _file(inputs: pathlib.Path, name: str, digest: str, fetch) -> bytes:
    path = inputs / name
    if path.exists() and cases.sha256(path.read_bytes()) == digest:
        return path.read_bytes()
    data = fetch()
    if cases.sha256(data) != digest:
        raise FetchError(f"{name}: its SHA-256 isn't the pinned one")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _transaction(inputs: pathlib.Path, rpc: str, h: str) -> dict:
    """A transaction in RPC JSON without its hash, which must hash to `h`."""
    path = inputs / "rpc" / f"{h}.json"
    tx = json.loads(path.read_text()) if path.exists() else _rpc(rpc, "get_transaction", [h])["transaction"]
    raw = rpc_json.transaction_from({k: v for k, v in tx.items() if k != "hash"}, h).raw
    if rpc_json.fmt_bytes(molecule.transaction_hash(raw)) != h or tx.get("hash") != h:
        raise FetchError(f"transaction {h} doesn't hash to itself")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tx, sort_keys=True))
    return {k: v for k, v in tx.items() if k != "hash"}


def _template(tx: dict, development_chain: bool, context: dict) -> dict:
    """The transaction with the lock removed from the first witness of each group version 1 signs."""
    out = dict(tx, witnesses=list(tx["witnesses"]))
    seen = set()
    for i, inp in enumerate(tx["inputs"]):
        op = inp["previous_output"]
        lock = context[op["tx_hash"]]["outputs"][int(op["index"], 16)]["lock"]
        key = json.dumps(lock, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        if scripts.lock_kind(rpc_json.script_from(lock, "lock"), development_chain) is None or i >= len(
            out["witnesses"]
        ):
            continue
        w = bytes.fromhex(out["witnesses"][i][2:])
        if not w:
            continue
        args = molecule.decode_witness_args(w)
        empty = args.input_type is None and args.output_type is None
        rest = molecule.WitnessArgs(None, args.input_type, args.output_type)
        out["witnesses"][i] = "0x" if empty else rpc_json.fmt_bytes(molecule.encode_witness_args(rest))
    return out


def _place(inp: dict, signatures: list[bytes]) -> list[dict]:
    """File each signature under the group and signer it recovers to, over that group's message."""
    accepted = reader.read(cases.encode(cases.sheet_from_input(inp)), False)
    placed = []
    for sig in signatures:
        for h, group in accepted.groups.items():
            if group.kind is None:
                continue
            try:
                signer = blake160(recover(message(accepted, group), sig))
            except InvalidSignature:
                continue
            if signer in (group.config.public_key_hashes if group.config else (group.lock.args,)):
                entry = {
                    "group": rpc_json.fmt_bytes(h),
                    "signer": rpc_json.fmt_bytes(signer),
                    "signature": rpc_json.fmt_bytes(sig),
                }
                if entry not in placed:
                    placed.append(entry)
    return sorted(placed, key=lambda e: (e["group"], e["signer"]))


def _config_json(r: int, m: int, keys: list[str]) -> tuple[str, dict]:
    c = MultisigConfig(r, m, tuple(bytes.fromhex(k[2:]) for k in keys))
    return rpc_json.fmt_bytes(c.key()), config_to_json(c)


def r1_input(inputs: pathlib.Path, digests: dict[str, str], rpc: str) -> dict:
    deploy = json.loads(
        _file(
            inputs,
            "fiber-scripts-pr34/mainnet.json",
            digests["fiber-scripts-pr34/mainnet.json"],
            lambda: _get(f"{GITHUB_RAW}/{DEPLOY_FILE}"),
        )
    )
    comments = None
    texts = []
    for n, cid in enumerate(COMMENTS, 1):
        name = f"fiber-scripts-pr34/comment-{n}.txt"

        def fetch_comment(cid=cid):
            nonlocal comments
            if comments is None:
                listed = json.loads(
                    _get(f"{GITHUB_API}/repos/nervosnetwork/fiber-scripts/issues/34/comments?per_page=100")
                )
                comments = {c["id"]: c for c in listed}
            return comments[cid]["body"].replace("\r\n", "\n").encode()

        texts.append(_file(inputs, name, digests[name], fetch_comment).decode())
    tx = deploy["cell_tx"]
    context = {}
    for i in tx["inputs"]:
        h = i["previous_output"]["tx_hash"]
        prev = deploy["used_input_txs"][h]
        context[h] = {k: prev[k] for k in rpc_json.RAW_FIELDS}
        raw = rpc_json.raw_transaction_from(context[h], h)
        if rpc_json.fmt_bytes(molecule.transaction_hash(raw)) != h:
            raise FetchError(f"the deploy file's input transaction {h} doesn't hash to its key")
    mc = deploy["deployment"]["multisig_config"]
    keys = []
    for a in mc["sighash_addresses"]:
        _, script = addresses.decode(a)
        if (script.code_hash, script.hash_type) != (scripts.SINGLE_KEY_CODE_HASH, "type"):
            raise FetchError("a multisig member address that isn't a single-key address")
        keys.append(rpc_json.fmt_bytes(script.args))
    key, config = _config_json(mc["require_first_n"], mc["threshold"], keys)
    _transaction(inputs, rpc, R1_COMMITTED)
    sigs = [bytes.fromhex(s[2:]) for v in deploy["cell_tx_signatures"].values() for s in v]
    for text in texts:
        sigs += [bytes.fromhex(s[2:]) for s in COMMENT_SIGNATURE.findall(text)]
    inp = {
        "chain": "mainnet",
        "source": SOURCES[R1],
        "transaction": _template({k: tx[k] for k in rpc_json.TRANSACTION_FIELDS}, False, context),
        "context": context,
        "headers": {},
        "inclusion_proofs": {},
        "multisig_configs": {key: config},
        "signatures": [],
        "recorded": {"committed": {"hash": R1_COMMITTED}},
    }
    inp["signatures"] = _place(inp, sigs)
    return inp


def r2_input(inputs: pathlib.Path, rpc: str) -> dict:
    tx = _transaction(inputs, rpc, R2_COMMITTED)
    context = {}
    for i in tx["inputs"]:
        h = i["previous_output"]["tx_hash"]
        context[h] = {k: v for k, v in _transaction(inputs, rpc, h).items() if k in rpc_json.RAW_FIELDS}
    lock = molecule.decode_witness_args(bytes.fromhex(tx["witnesses"][0][2:])).lock
    r, m, n = lock[1], lock[2], lock[3]
    keys = [rpc_json.fmt_bytes(lock[4 + 20 * i : 24 + 20 * i]) for i in range(n)]
    key, config = _config_json(r, m, keys)
    sigs = [lock[4 + 20 * n + 65 * j : 4 + 20 * n + 65 * (j + 1)] for j in range(m)]
    inp = {
        "chain": "mainnet",
        "source": SOURCES[R2],
        "transaction": _template(tx, False, context),
        "context": context,
        "headers": {},
        "inclusion_proofs": {},
        "multisig_configs": {key: config},
        "signatures": [],
        "recorded": {"committed": {"hash": R2_COMMITTED, "witnesses": tx["witnesses"]}},
    }
    inp["signatures"] = _place(inp, sigs)
    return inp


def summary(case_id: str, files: dict[str, bytes]) -> dict:
    """What the repository keeps of a mainnet case: no chain data, only hashes and digests."""
    expected = canonical.check(files["expected.json"])
    final = files.get("final-tx.json")
    final_hash = None
    if final is not None:
        tx = rpc_json.transaction_from(canonical.check(final), "final")
        final_hash = rpc_json.fmt_bytes(molecule.transaction_hash(tx.raw))
    return {
        "id": case_id,
        "source": SOURCES[case_id],
        "outcome": expected["outcome"],
        "unsigned_id": expected["unsigned_id"],
        "messages": expected["messages"],
        "ready": expected["ready"],
        "final_transaction_hash": final_hash,
        "files": {name: cases.sha256(b) for name, b in sorted(files.items())},
    }


def run(root: pathlib.Path, rpc: str, record: bool) -> int:
    fetched = root / "mainnet" / ".fetched"
    inputs = fetched / "inputs"
    digests = pinned_digests(root)
    problems = []
    for case_id, make in ((R1, lambda: r1_input(inputs, digests, rpc)), (R2, lambda: r2_input(inputs, rpc))):
        files = cases.build(case_id, canonical.encode(make()))
        out = fetched / case_id
        for name, data in files.items():
            (out / name).parent.mkdir(parents=True, exist_ok=True)
            (out / name).write_bytes(data)
        got = summary(case_id, files)
        path = root / "mainnet" / case_id / "expected.json"
        if record:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(canonical.encode(got))
            print(f"{case_id}: recorded vectors/mainnet/{case_id}/expected.json")
            continue
        want = canonical.check(path.read_bytes())
        for field in sorted(set(want) | set(got)):
            if want.get(field) != got.get(field):
                problems.append(f"{case_id}: {field} differs from vectors/mainnet/{case_id}/expected.json")
        print(f"{case_id}: {len(files)} files rebuilt, final transaction {got['final_transaction_hash']}")
    for p in problems:
        print(p)
    print(
        "fetch-mainnet: R1 and R2 match their expected values"
        if not problems
        else f"fetch-mainnet: {len(problems)} differences"
    )
    return 1 if problems else 0
