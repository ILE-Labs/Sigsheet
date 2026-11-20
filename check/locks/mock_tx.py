"""Builds a ckb-debugger mock transaction for a vector's transaction, from the vector's own files and the code cells.

The form is ckb-debugger v1.1.1's (https://github.com/nervosnetwork/ckb-standalone-debugger/blob/740d6de0c1d7c2394a492f9bfef57e77abb98dfd/ckb-debugger/examples/mock_tx.json):
`mock_info.inputs`, each input with the output it spends and that output's data; `mock_info.cell_deps`, every cell dep
of the transaction and every cell a dep group lists, each once; `mock_info.header_deps`, every header dep as a header
with its hash; and `tx`, the transaction with exactly its seven fields. Binaries come from `code-cells.json`: fetched
read-only from mainnet once, checked by their data hash, and kept in `.work/`.
"""

import hashlib
import json
import pathlib
import urllib.request

USER_AGENT = "Mozilla/5.0"
TX_FIELDS = ("version", "cell_deps", "header_deps", "inputs", "outputs", "outputs_data", "witnesses")


def ckbhash(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=32, person=b"ckb-default-hash").digest()


def key(out_point: dict) -> tuple[str, int]:
    return out_point["tx_hash"], int(out_point["index"], 16)


class CodeCells:
    def __init__(self, path: pathlib.Path, work: pathlib.Path, rpc: str):
        self.cells = {key(c["out_point"]): c for c in json.loads(path.read_bytes())["cells"]}
        self.work = work
        self.rpc = rpc
        self._fetched: dict[str, dict] = {}

    def _transaction(self, tx_hash: str) -> dict:
        if tx_hash not in self._fetched:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "get_transaction", "params": [tx_hash]}).encode(
                "ascii"
            )
            req = urllib.request.Request(
                self.rpc, data=body, headers={"Content-Type": "application/json", "User-Agent": USER_AGENT}
            )
            with urllib.request.urlopen(req, timeout=300) as r:
                out = json.loads(r.read())
            if "error" in out:
                raise RuntimeError(f"get_transaction {tx_hash}: {out['error']}")
            self._fetched[tx_hash] = out["result"]["transaction"]
        return self._fetched[tx_hash]

    def data(self, cell: dict) -> str:
        if "data" in cell:
            data = bytes.fromhex(cell["data"][2:])
        else:
            cached = self.work / f"{cell['data_hash'][2:]}.bin"
            if cached.exists():
                data = cached.read_bytes()
            else:
                src = cell["data_from"]
                data = bytes.fromhex(self._transaction(src["tx_hash"])["outputs_data"][int(src["index"], 16)][2:])
        if "0x" + ckbhash(data).hex() != cell["data_hash"]:
            raise RuntimeError(f"code cell {cell['out_point']}: the data doesn't hash to {cell['data_hash']}")
        if "data" not in cell:
            self.work.mkdir(parents=True, exist_ok=True)
            (self.work / f"{cell['data_hash'][2:]}.bin").write_bytes(data)
        return "0x" + data.hex()

    def entry(self, out_point: dict, dep_type: str) -> dict:
        cell = self.cells.get(key(out_point))
        if cell is None or cell["dep_type"] != dep_type:
            raise RuntimeError(f"no {dep_type} code cell at {out_point} in code-cells.json")
        cell_dep = {"out_point": out_point, "dep_type": dep_type}
        return {"cell_dep": cell_dep, "output": cell["output"], "data": self.data(cell), "header": None}


def out_points(group_data: str) -> list[dict]:
    """A dep group's data: an OutPointVec, a u32 count then 36-byte out points (tx hash, u32 index)."""
    b = bytes.fromhex(group_data[2:])
    n = int.from_bytes(b[:4], "little")
    if len(b) != 4 + 36 * n:
        raise RuntimeError("a dep group's data isn't an OutPointVec")
    points = []
    for i in range(n):
        item = b[4 + 36 * i : 40 + 36 * i]
        points.append({"tx_hash": "0x" + item[:32].hex(), "index": hex(int.from_bytes(item[32:], "little"))})
    return points


def mock(tx: dict, sheet: dict, cells: CodeCells) -> dict:
    inputs = []
    for i in tx["inputs"]:
        op = i["previous_output"]
        prev = sheet["context"][op["tx_hash"]]
        index = int(op["index"], 16)
        inputs.append(
            {"input": i, "output": prev["outputs"][index], "data": prev["outputs_data"][index], "header": None}
        )
    deps: list[dict] = []
    for dep in tx["cell_deps"]:
        entries = [cells.entry(dep["out_point"], dep["dep_type"])]
        if dep["dep_type"] == "dep_group":
            entries += [cells.entry(p, "code") for p in out_points(entries[0]["data"])]
        for e in entries:
            if all(d["cell_dep"] != e["cell_dep"] for d in deps):
                deps.append(e)
    headers = [dict(sheet["headers"][h], hash=h) for h in tx["header_deps"]]
    return {
        "mock_info": {"inputs": inputs, "cell_deps": deps, "header_deps": headers},
        "tx": {k: tx[k] for k in TX_FIELDS},
    }
