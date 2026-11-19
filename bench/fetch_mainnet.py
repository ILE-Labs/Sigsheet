"""Fetch the public mainnet inputs the offline benchmarks need, then rebuild the mainnet case files.

Optional and the only step that uses the network: read-only GETs and JSON-RPC reads of public sources at pinned
versions, with a generic User-Agent.
- CKB mainnet JSON-RPC (default https://mainnet.ckb.dev/, the public endpoint docs.nervos.org lists):
  `get_transaction` for R2 (a 2-of-3 genesis multisig payment), its previous transaction, and PR #34's committed transaction.
  Every transaction hash is recomputed with experiments/X1/scripts/ckbcore.py and must match.
- GitHub: fiber-scripts' deploy file at commit 026027f (its SHA-256 must match), and PR #34's four signature
  comments, by comment id (each file's SHA-256 must match experiments/mainnet-inputs.sha256).
Then it rebuilds the case files from them with the experiments' own scripts and checks every rebuilt file against
experiments/mainnet-inputs.sha256.

Usage, from the repository root:  ./bench/fetch-mainnet.sh [--rpc URL] [--github-raw URL] [--github-api URL]
                                                         [--comments-only] [--no-build]
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXP = ROOT / "experiments"
X1 = EXP / "X1"
sys.path.insert(0, str(X1 / "scripts"))
import ckbcore as c  # noqa: E402

UA = "research-script/1.0"
PAYOUT = "0x63a7f3a52fc91c52939186ca9c1064238ccdfe498d3398f25707537f591bbaa4"
PR34_COMMITTED = "0x4396de69818bd88b7fce64797ccec25d1294912d56846432f29fd192120992ee"
DEPLOY = ("nervosnetwork/fiber-scripts/026027f54f6a90cb48d8cc184b230e2018bb8611/deployment/mainnet/mainnet.json",
          "8563ba8dcd0d051822dd0cc21db995dc8e6a2984e900d3500068f0185a07b51e")
COMMENTS = [6571892250, 6573354672, 6581601897, 6605978601]  # PR #34's four signature comments, in order
MANIFEST = EXP / "mainnet-inputs.sha256"


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def manifest():
    out = {}
    for line in MANIFEST.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            digest, path = line.split(None, 1)
            out[path.strip()] = digest
    return out


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, */*"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def rpc(url, method, params):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    if "error" in out:
        raise SystemExit(f"{method} {params}: {out['error']}")
    time.sleep(1)  # one call a second, to be gentle with a public endpoint
    return out["result"]


def fetch_tx(url, h):
    """Write experiments/X1/data/mainnet/<hash>.json in the format X1's fetch_mainnet.py writes."""
    res = rpc(url, "get_transaction", [h])
    tx = res["transaction"]
    mine = c.b2h(c.tx_hash(tx))
    if mine != tx["hash"] or mine != h:
        raise SystemExit(f"hash mismatch for {h}: the encoder gives {mine}")
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    path = X1 / "data" / "mainnet" / f"{h}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"rpc": url, "method": "get_transaction", "params": [h], "fetched": now,
                                "hash_check": "ckbcore.tx_hash matches", "result": res}, indent=1))
    print(f"  {h}  hash checked")
    return tx


def fetch_comments(api, expected):
    data = json.loads(get(f"{api}/repos/nervosnetwork/fiber-scripts/issues/34/comments?per_page=100"))
    by_id = {x["id"]: x for x in data}
    folder = X1 / "data" / "fiber-scripts-34"
    folder.mkdir(parents=True, exist_ok=True)
    for n, cid in enumerate(COMMENTS, 1):
        body = by_id[cid]["body"].replace("\r\n", "\n").encode()
        rel = f"experiments/X1/data/fiber-scripts-34/comment-{n}.txt"
        if sha256(body) != expected[rel]:
            raise SystemExit(f"comment {cid} has changed since it was recorded ({rel})")
        (folder / f"comment-{n}.txt").write_bytes(body)
        print(f"  comment-{n}.txt  (comment {cid}) SHA-256 checked")


def run(args, cwd, stdout_to=None):
    cmd = [sys.executable, "-I", "-B", "-X", "utf8", *args]
    if stdout_to:
        with open(stdout_to, "w") as out:
            subprocess.run(cmd, cwd=str(cwd), check=True, stdout=out)
    else:
        subprocess.run(cmd, cwd=str(cwd), check=True, stdout=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rpc", default="https://mainnet.ckb.dev/")
    ap.add_argument("--github-raw", default="https://raw.githubusercontent.com")
    ap.add_argument("--github-api", default="https://api.github.com")
    ap.add_argument("--comments-only", action="store_true", help="only PR #34's four signature comments")
    ap.add_argument("--no-build", action="store_true", help="fetch only; don't rebuild the case files")
    a = ap.parse_args()
    expected = manifest()
    print("PR #34's signature comments (GitHub API):")
    fetch_comments(a.github_api.rstrip("/"), expected)
    if a.comments_only:
        return
    print("The PR #34 deploy file (GitHub, pinned commit):")
    body = get(f"{a.github_raw.rstrip('/')}/{DEPLOY[0]}")
    if sha256(body) != DEPLOY[1]:
        raise SystemExit("the deploy file's SHA-256 doesn't match")
    (X1 / "data" / "fiber-scripts-34" / "mainnet.json").write_bytes(body)
    print("  mainnet.json  SHA-256 checked")
    print("Mainnet transactions (JSON-RPC, read-only):")
    payout = fetch_tx(a.rpc, PAYOUT)
    for i in payout["inputs"]:
        fetch_tx(a.rpc, i["previous_output"]["tx_hash"])
    fetch_tx(a.rpc, PR34_COMMITTED)
    if a.no_build:
        return
    print("Rebuilding the mainnet case files with the experiments' scripts:")
    run(["scripts/build_cases.py", "--real-only"], X1)
    run(["cases.py"], EXP / "prototypes")
    run(["scripts/build_partials.py"], EXP / "X3a", stdout_to=EXP / "X3a" / "results" / "partials.json")
    run(["make_a_check.py"], EXP / "X6" / "interop")
    bad = 0
    for rel, digest in sorted(expected.items()):
        p = ROOT / rel
        if not p.exists() or not digest or digest == "-":
            continue
        ok = sha256(p.read_bytes()) == digest
        bad += not ok
        print(f"  {'OK  ' if ok else 'DIFF'}  {rel}")
    if bad:
        raise SystemExit(f"{bad} file(s) differ from experiments/mainnet-inputs.sha256")
    print("Done. ./bench/run.sh now runs the mainnet cases too.")


if __name__ == "__main__":
    main()
