"""Writes `vectors/` and its `index.json`, and compares a rebuild with what is on disk, byte for byte.

The recorded inputs (every `input.json`, `vectors/mainnet/inputs.sha256`, each `vectors/mainnet/<id>/expected.json`)
and `vectors/README.md` are read, never written, by `build`; every other file is `build`'s output. Files are written
as their exact bytes, with no trailing newline; no formatter may touch them.
"""

import pathlib

from ..sigsheet import canonical
from .cases import sha256

RECORDED_NAMES = ("input.json",)
FETCHED = "mainnet/.fetched"


def recorded(path: str) -> bool:
    """Whether a path inside vectors/ is a recorded input or documentation, which build reads but never writes."""
    parts = path.split("/")
    if path in ("README.md", "mainnet/inputs.sha256") or parts[-1] in RECORDED_NAMES:
        return True
    return len(parts) == 3 and parts[0] == "mainnet" and parts[2] == "expected.json"


def on_disk(root: pathlib.Path) -> dict[str, bytes]:
    out = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and not rel.startswith(FETCHED + "/"):
            out[rel] = p.read_bytes()
    return out


def index(entries: list[dict], files: dict[str, bytes]) -> bytes:
    """`index.json`: every vector with its kind, chain, source experiment and the SHA-256 of each of its files."""
    vectors = []
    for e in entries:
        prefix = f"{e['folder']}/"
        names = {k[len(prefix) :]: sha256(v) for k, v in sorted(files.items()) if k.startswith(prefix)}
        vectors.append({"id": e["id"], "kind": e["kind"], "chain": e["chain"], "source": e["source"], "files": names})
    return canonical.encode({"vectors": vectors})


def differences(root: pathlib.Path, built: dict[str, bytes]) -> list[str]:
    disk = on_disk(root)
    problems = []
    for path, data in sorted(built.items()):
        if path not in disk:
            problems.append(f"missing: {path}")
        elif disk[path] != data:
            problems.append(f"differs: {path}")
    for path in sorted(set(disk) - set(built)):
        if not recorded(path):
            problems.append(f"not built by the generator: {path}")
    return problems


def write(root: pathlib.Path, built: dict[str, bytes]) -> None:
    disk = on_disk(root)
    for path in sorted(set(disk) - set(built)):
        if not recorded(path):
            (root / path).unlink()
    for path, data in sorted(built.items()):
        target = root / path
        if recorded(path):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if disk.get(path) != data:
            target.write_bytes(data)
    for d in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
