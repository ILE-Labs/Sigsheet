"""The command line.

    python -m sigsheet_vectors build            rebuild every vector into vectors/ from its recorded input
    python -m sigsheet_vectors check            rebuild in memory and compare every byte and index.json with vectors/
    python -m sigsheet_vectors fetch-mainnet    fetch the two mainnet cases read-only, rebuild them under
                                                vectors/mainnet/.fetched/ and check them against vectors/mainnet/

`build` and `check` read only vectors/ and use no randomness, clock, network or environment variable. The vectors
folder is found from this package's location, so they run the same from any working directory.
"""

import argparse
import pathlib
import sys

from .sigsheet import canonical
from .vectors import attacks, cases, writer

ROOT = pathlib.Path(__file__).resolve().parents[2] / "vectors"


def build_all(root: pathlib.Path) -> dict[str, bytes]:
    """Every file `build` writes, and the recorded ones it reads, by path inside vectors/."""
    files: dict[str, bytes] = {}
    entries = []
    built: dict[str, dict[str, bytes]] = {}
    chains: dict[str, str] = {}
    for case in cases.CASES:
        folder = f"cases/{case.id}"
        input_bytes = (root / folder / "input.json").read_bytes()
        chains[case.id] = canonical.check(input_bytes)["chain"]
        built[case.id] = cases.build(case.id, input_bytes, case.expect)
        files.update({f"{folder}/{name}": b for name, b in built[case.id].items()})
        entries.append(
            {"id": case.id, "kind": "case", "chain": chains[case.id], "source": case.source, "folder": folder}
        )
    for attack in attacks.ATTACKS:
        folder = f"attacks/{attack.id}"
        input_bytes = (root / folder / "input.json").read_bytes()
        inp = canonical.check(input_bytes)
        vector = attacks.build(attack, input_bytes, built, chains)
        files.update({f"{folder}/{name}": b for name, b in vector.items()})
        chain = chains[inp["base"]] if inp.get("base") else inp["chain"]
        entries.append({"id": attack.id, "kind": "attack", "chain": chain, "source": inp["source"], "folder": folder})
    mainnet = root / "mainnet"
    if (mainnet / "inputs.sha256").exists():
        files["mainnet/inputs.sha256"] = (mainnet / "inputs.sha256").read_bytes()
    for expected in sorted(mainnet.glob("*/expected.json")):
        case_id = expected.parent.name
        files[f"mainnet/{case_id}/expected.json"] = expected.read_bytes()
        source = canonical.check(expected.read_bytes())["source"]
        entries.append(
            {"id": case_id, "kind": "mainnet", "chain": "mainnet", "source": source, "folder": f"mainnet/{case_id}"}
        )
    files["index.json"] = writer.index(entries, files)
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m sigsheet_vectors", description="Build and check the Sigsheet vectors."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build", help="rebuild every vector into vectors/")
    sub.add_parser("check", help="rebuild in memory and compare every byte with vectors/")
    fetch = sub.add_parser("fetch-mainnet", help="fetch and check the two mainnet cases")
    fetch.add_argument("--rpc", default="https://mainnet.ckb.dev/", help="a CKB mainnet JSON-RPC endpoint")
    fetch.add_argument("--record", action="store_true", help="write vectors/mainnet/<id>/expected.json from this fetch")
    args = parser.parse_args(argv)

    if args.command == "build":
        files = build_all(ROOT)
        writer.write(ROOT, files)
        print(f"built {sum(1 for p in files if not writer.recorded(p))} files in {ROOT.name}/")
        return 0
    if args.command == "check":
        problems = writer.differences(ROOT, build_all(ROOT))
        for p in problems:
            print(p)
        print("check: every vector rebuilds byte for byte" if not problems else f"check: {len(problems)} differences")
        return 1 if problems else 0
    from .mainnet import fetch as mainnet_fetch

    return mainnet_fetch.run(ROOT, args.rpc, args.record)


if __name__ == "__main__":
    sys.exit(main())
