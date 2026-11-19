#!/usr/bin/env python3
"""X6: measure each wallet's Sigsheet patch (files, lines, code lines) from fresh pristine copies, and write the diffs.

Usage, from experiments/X6:  python3 -I -X utf8 measure.py > results/measure.json
Pristine copies are re-extracted with `git archive` from the pinned clones in refs/ (which stay untouched), into a
temporary folder; each diff is written to <wallet>/patch.diff with paths relative to the wallet's source root.
"Code lines" are added lines that are neither blank nor comment-only (// , /*, *, //! and /// lines).
"""
import json
import pathlib
import re
import subprocess
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
INV = HERE.parent.parent
WALLETS = {
    "ckb-cli": ("ckb-cli", "80efc21c30e9fc7847407a217034681b6e46c763", "src", HERE / "ckb-cli" / "src-copy" / "src"),
    "CCC": ("ccc", "7095ccad564b94ea2e59284cb4a364aa3499252e", "packages/core/src", HERE / "ccc" / "core" / "src"),
    "Neuron": ("neuron", "d3a7467d218e4b6f777326682a83fec802669c00", "packages/neuron-wallet/src",
               HERE / "neuron" / "packages" / "neuron-wallet" / "src"),
}
COMMENT = re.compile(r"^\s*(//|/\*|\*|\*/)")


def main():
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for name, (repo, commit, path, patched) in WALLETS.items():
            pristine = pathlib.Path(tmp) / name
            pristine.mkdir()
            arch = subprocess.run(["git", "-C", str(INV / "refs" / repo), "archive", commit, path],
                                  capture_output=True, check=True).stdout
            subprocess.run(["tar", "-x", "-C", str(pristine), "--strip-components", str(path.count("/"))],
                           input=arch, check=True)
            d = subprocess.run(["git", "diff", "--no-index", "--no-color", "src", str(patched)], cwd=pristine,
                               capture_output=True, text=True).stdout
            d = d.replace("b" + str(patched), "b/src")
            target = {"ckb-cli": HERE / "ckb-cli" / "patch.diff", "CCC": HERE / "ccc" / "patch.diff",
                      "Neuron": HERE / "neuron" / "patch.diff"}[name]
            target.write_text(d)
            files, added, removed, code = {}, 0, 0, 0
            current = None
            for line in d.splitlines():
                if line.startswith("+++ "):
                    current = line[4:].replace("b/", "", 1)
                    files.setdefault(current, {"added": 0, "removed": 0, "code_added": 0})
                elif line.startswith("--- "):
                    continue
                elif line.startswith("+") and current:
                    files[current]["added"] += 1
                    added += 1
                    body = line[1:]
                    if body.strip() and not COMMENT.match(body):
                        files[current]["code_added"] += 1
                        code += 1
                elif line.startswith("-") and current:
                    files[current]["removed"] += 1
                    removed += 1
            out[name] = {"commit": commit, "files": files, "files_changed": len(files), "lines_added": added,
                         "lines_removed": removed, "code_lines_added": code}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
