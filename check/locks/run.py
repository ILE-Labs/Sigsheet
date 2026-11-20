"""Runs every final transaction's signed lock groups through ckb-debugger with the deployed binaries, and the controls.

For each vector folder with a `final-tx.json`, each lock group of a kind version 1 signs (from `expected.json`) is run
as `ckb-debugger --tx-file <mock> --script input.<its first input>.lock` and must print `Run result: 0`. The controls
reproduce the chain's other verdicts from the vectors' own signatures: a signature's high-s twin is accepted (S1);
the two signatures of S4N, without the required first member, are rejected; and the genesis binary rejects position
10 when M <= 10 and position 18 when M = 1, while accepting the set finalize picks instead.

    python check/locks/run.py [--debugger PATH] [--rpc URL] <vector folder>...

Binaries are fetched read-only from mainnet once and kept in check/locks/.work/; nothing else uses the network.
"""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys

from mock_tx import CodeCells, mock

HERE = pathlib.Path(__file__).resolve().parent
WORK = HERE / ".work"
# The secp256k1 group order, for the high-s twin s -> N - s
# (https://github.com/nervosnetwork/secp256k1/blob/3ffde18a060aaf4df5b81e7d88355f1e99874650/src/scalar_4x64_impl.h#L11-L14).
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
# Vector id -> the member positions whose signatures form a set the chain rejects.
REJECTED_SETS = {
    "S4N-v2-first-R-missing-required": (1, 2),
    "genesis-n12-m2-skip-10": (5, 10),
    "genesis-n12-m2-10-11-not-ready": (10, 11),
    "genesis-n20-m1-18-not-ready": (18,),
}


def read(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="ascii"))


def witness_with_lock(lock: bytes) -> str:
    """A WitnessArgs holding only a lock: a table of three BytesOpt fields, the last two absent."""
    size = 16 + 4 + len(lock)
    parts = [size, 16, 20 + len(lock), 20 + len(lock), len(lock)]
    return "0x" + (b"".join(x.to_bytes(4, "little") for x in parts) + lock).hex()


def run(debugger: str, mock_tx: dict, input_index: int, name: str) -> tuple[bool, str]:
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / f"{name}.json"
    path.write_bytes(json.dumps(mock_tx).encode("ascii"))
    p = subprocess.run(
        [debugger, "--tx-file", str(path), "--script", f"input.{input_index}.lock"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    line = next((x for x in p.stdout.splitlines() if x.startswith("Run result:")), (p.stdout + p.stderr).strip()[-200:])
    return p.returncode == 0 and line == "Run result: 0", line


def forced(sheet: dict, group: dict, positions: tuple[int, ...]) -> dict:
    """The file's transaction with the group's lock written from the signatures at `positions`, in member order."""
    config = sheet["multisig_configs"][_args(sheet, group)[:42]]
    members = config["public_key_hashes"]
    script = bytes([0, config["require_first_n"], config["threshold"], len(members)]) + b"".join(
        bytes.fromhex(k[2:]) for k in members
    )
    sigs = sheet["signatures"][group["lock_hash"]]
    lock = script + b"".join(bytes.fromhex(sigs[members[p]][2:]) for p in positions)
    tx = json.loads(json.dumps(sheet["transaction"]))
    tx["witnesses"][group["inputs"][0]] = witness_with_lock(lock)
    return tx


def _args(sheet: dict, group: dict) -> str:
    op = sheet["transaction"]["inputs"][group["inputs"][0]]["previous_output"]
    return sheet["context"][op["tx_hash"]]["outputs"][int(op["index"], 16)]["lock"]["args"]


def high_s_twin(sig: bytes) -> bytes:
    s = int.from_bytes(sig[32:64], "big")
    return sig[:32] + (N - s).to_bytes(32, "big") + bytes([sig[64] ^ 1])


def vector_folders(root: pathlib.Path) -> list[pathlib.Path]:
    if (root / "expected.json").exists():
        return [root]
    subs = [p for p in sorted(root.iterdir()) if p.is_dir() and not p.name.startswith(".") and p.name != "partial"]
    return [f for p in subs for f in vector_folders(p)]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--debugger", default="ckb-debugger")
    parser.add_argument("--rpc", default="https://mainnet.ckb.dev/")
    parser.add_argument("folders", nargs="+", type=pathlib.Path)
    args = parser.parse_args(argv)
    # The debugger by its full path: `shutil.which` also finds `ckb-debugger.exe` on Windows from a name without it,
    # and a relative path works the same on every system.
    found = shutil.which(args.debugger)
    if found is None:
        print(f"locks: no ckb-debugger at {args.debugger}")
        return 1
    args.debugger = str(pathlib.Path(found).resolve())
    cells = CodeCells(HERE / "code-cells.json", WORK / "binaries", args.rpc)
    problems, ran, controls = [], 0, 0
    for folder in [f for root in args.folders for f in vector_folders(root)]:
        expected = read(folder / "expected.json")
        if expected.get("outcome") != "accepted" or "shown" not in expected:
            continue
        sheet = read(folder / ("attack.json" if (folder / "attack.json").exists() else "merged.json"))
        groups = [g for g in expected["shown"]["groups"] if g["kind"] != "carried"]
        final = folder / "final-tx.json"
        if final.exists():
            tx = read(final)
            for g in groups:
                ok, line = run(args.debugger, mock(tx, sheet, cells), g["inputs"][0], f"{folder.name}-{g['inputs'][0]}")
                ran += 1
                if not ok:
                    problems.append(f"{folder.name}: input.{g['inputs'][0]}.lock gives {line!r}, not 0")
        if folder.name == "S1-genesis-2of3" and final.exists():
            (g,) = groups
            tx = read(final)
            w = bytes.fromhex(tx["witnesses"][g["inputs"][0]][2:])
            n = w[20 + 3]
            start = 20 + 4 + 20 * n
            w = w[:start] + high_s_twin(w[start : start + 65]) + w[start + 65 :]
            tx["witnesses"][g["inputs"][0]] = "0x" + w.hex()
            ok, line = run(args.debugger, mock(tx, sheet, cells), g["inputs"][0], "control-high-s-twin")
            controls += 1
            if not ok:
                problems.append(f"control: the high-s twin gives {line!r}; the chain accepted it")
        if folder.name in REJECTED_SETS:
            (g,) = groups
            tx = forced(sheet, g, REJECTED_SETS[folder.name])
            ok, line = run(args.debugger, mock(tx, sheet, cells), g["inputs"][0], f"control-{folder.name}")
            controls += 1
            if ok or line != "Run result: -52":
                problems.append(
                    f"control {folder.name} {REJECTED_SETS[folder.name]}: {line!r}; the chain rejected it with -52"
                )
    for p in problems:
        print(p)
    print(f"locks: {ran} lock groups run, {controls} controls, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
