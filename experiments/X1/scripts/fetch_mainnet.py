#!/usr/bin/env python3
"""Fetch the mainnet data X1 needs from a public CKB RPC node, read-only, and check every transaction hash.

Usage, from experiments/X1:
    python3 -I -X utf8 scripts/fetch_mainnet.py [rpc url]     # default https://mainnet.ckb.dev/

The RPC endpoint comes from the official docs (website/docs/getting-started/rpcs.mdx in
nervosnetwork/docs.nervos.org; a saved copy is in sources/). The calls are JSON-RPC reads only:
get_transaction, get_block_by_number, get_header.

It saves each transaction to data/mainnet/<hash>.json, with the RPC URL and fetch time, and
checks that the hash this folder's own encoder computes (scripts/ckbcore.py) equals the hash the
node returns. Then it records the three multisig deployments: the dep group cell, the code cell
it points to, the code cell's data hash and type script hash.
"""
import datetime
import json
import pathlib
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ckbcore as c  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent.parent
OUT = HERE / "data" / "mainnet"
RPC = sys.argv[1] if len(sys.argv) > 1 else "https://mainnet.ckb.dev/"
UA = "research-script/1.0"

PAYOUT = "0x63a7f3a52fc91c52939186ca9c1064238ccdfe498d3398f25707537f591bbaa4"
# fiber-scripts PR #34: the cell_tx of deployment/mainnet/mainnet.json at 026027f, committed after 2026-11-08
PR34 = "0x4396de69818bd88b7fce64797ccec25d1294912d56846432f29fd192120992ee"
DEPLOYMENTS = {  # name: (expected code hash, hash type, dep group out point) from CCC's mainnet table
    "genesis": ("0x5c5069eb0857efc65e1bca0c07df34c31663b3622fd3876c876320fc9634e2a8", "type",
                ("0x71a7ba8fc96349fea0ed3a5c47992e3b4084b031a42264a018e0072e8172e46c", 1)),
    "2024": ("0xd1a9f877aed3f5e07cb9c52b61ab96d06f250ae6883cc7f0a2423db0976fc821", "type",
             ("0x44be4f4feda80c0e41783ab10e191df3b2bb5c3731b0970c916dbec385dcdc60", 0)),
    "v2": ("0x36c971b8d41fbd94aabca77dc75e826729ac98447b46f91e00796155dddb0d29", "data1",
           ("0x6888aa39ab30c570c2c30d9d5684d3769bf77265a7973211a3c087fe8efbf738", 0)),
}
_last = [0.0]


def rpc(method, params):
    wait = _last[0] + 1.0 - time.time()
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type": "application/json",
                                                         "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise RuntimeError(f"{method} {params}: {out['error']}")
    return out["result"]


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def get_tx(h):
    path = OUT / f"{h}.json"
    if path.exists():
        return json.loads(path.read_text())["result"]
    res = rpc("get_transaction", [h])
    tx = res["transaction"]
    mine = c.b2h(c.tx_hash(tx))
    if mine != tx["hash"] or mine != h:
        raise SystemExit(f"hash mismatch for {h}: encoder gives {mine}")
    path.write_text(json.dumps({"rpc": RPC, "method": "get_transaction", "params": [h],
                                "fetched": now(), "hash_check": "ckbcore.tx_hash matches",
                                "result": res}, indent=1))
    return res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"rpc": RPC, "fetched": now(), "transactions": {}, "deployments": {}}

    # 1. R2, the genesis 2-of-3 payment: its block and every input's creating transaction.
    res = get_tx(PAYOUT)
    blk = res["tx_status"]["block_hash"]
    header = rpc("get_header", [blk])
    (OUT / "payout-block-header.json").write_text(json.dumps({"rpc": RPC, "fetched": now(),
                                                              "result": header}, indent=1))
    report["transactions"]["payout"] = {"hash": PAYOUT, "block_hash": blk,
                                        "block_number": int(header["number"], 16),
                                        "timestamp_ms": int(header["timestamp"], 16)}
    for i in res["transaction"]["inputs"]:
        get_tx(i["previous_output"]["tx_hash"])

    # 1b. The fiber-scripts PR #34 transaction, if it's on chain, and its block.
    res34 = get_tx(PR34)
    if res34["tx_status"]["status"] == "committed":
        h34 = rpc("get_header", [res34["tx_status"]["block_hash"]])
        report["transactions"]["pr34"] = {"hash": PR34, "block_hash": h34["hash"],
                                          "block_number": int(h34["number"], 16),
                                          "timestamp_ms": int(h34["timestamp"], 16)}
    else:
        report["transactions"]["pr34"] = {"hash": PR34, "status": res34["tx_status"]["status"]}

    # 2. The genesis block's two transactions hold the genesis system cells and dep groups.
    g = rpc("get_block_by_number", ["0x0"])
    for tx in g["transactions"]:
        if c.b2h(c.tx_hash(tx)) != tx["hash"]:
            raise SystemExit("genesis hash mismatch")
    (OUT / "genesis-block.json").write_text(json.dumps({"rpc": RPC, "fetched": now(),
                                                        "result": g}, indent=1))
    genesis = {tx["hash"]: tx for tx in g["transactions"]}

    def tx_of(h):
        return genesis[h] if h in genesis else get_tx(h)["transaction"]

    # 3. Each deployment: dep group cell -> the out points it lists -> the code cells.
    for name, (code_hash, hash_type, (dep_tx, dep_index)) in DEPLOYMENTS.items():
        dtx = tx_of(dep_tx)
        data = c.h2b(dtx["outputs_data"][dep_index])
        count = int.from_bytes(data[:4], "little")
        points = [(c.b2h(data[4 + 36 * k: 36 + 36 * k]),
                   int.from_bytes(data[36 + 36 * k: 40 + 36 * k], "little")) for k in range(count)]
        cells = []
        for th, idx in points:
            ctx = tx_of(th)
            out, cdata = ctx["outputs"][idx], c.h2b(ctx["outputs_data"][idx])
            cells.append({
                "out_point": f"{th}:{idx}",
                "data_bytes": len(cdata),
                "data_hash": c.b2h(c.ckbhash(cdata)),
                "type_script": out.get("type"),
                "type_script_hash": c.b2h(c.script_hash(out["type"])) if out.get("type") else None,
            })
        match = [x for x in cells if (x["type_script_hash"] if hash_type == "type" else x["data_hash"])
                 == code_hash]
        report["deployments"][name] = {
            "expected_code_hash": code_hash, "hash_type": hash_type,
            "dep_group": f"{dep_tx}:{dep_index}", "dep_group_lists": cells,
            "multisig_code_cell": match[0] if match else None,
            "code_hash_confirmed": bool(match),
        }
        if match:
            binary = c.h2b(tx_of(match[0]["out_point"].split(":")[0])["outputs_data"][
                int(match[0]["out_point"].split(":")[1])])
            (OUT / f"multisig-{name}.bin").write_bytes(binary)

    (OUT / "summary.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: {kk: v[kk] for kk in ("code_hash_confirmed", "hash_type")}
                      for k, v in report["deployments"].items()}, indent=1))
    for k, v in report["deployments"].items():
        m = v["multisig_code_cell"]
        if m:
            print(k, m["out_point"], m["data_bytes"], "bytes; data hash", m["data_hash"],
                  "; type hash", m["type_script_hash"])
    print("payout", report["transactions"]["payout"])


if __name__ == "__main__":
    main()
