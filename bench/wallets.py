"""Optional: check each design-stage wallet diff against its upstream source, and count it.

For ckb-cli, CCC and Neuron: clone the repository at its pinned commit (only if refs/<name> doesn't exist yet: the
one step that uses the network), extract a pristine copy with `git archive`, apply the diff with `patch -p1`, and
count the lines it adds the way experiments/X6/measure.py does; then compare with experiments/X6/results/measure.json.
The same for the ckb-cli creation diff (XRT-4), applied on top of X6's. Building each wallet and running its own
tests is described in experiments/X6/README.md.

Usage, from the repository root:  ./bench/wallets.sh [--refs DIR]   (DIR defaults to refs/)
"""
import argparse
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXP = ROOT / "experiments"
sys.path.insert(0, str(ROOT / "bench" / "lib"))
import line_count  # noqa: E402

WALLETS = [  # name, folder under refs/, URL, commit, the path the diff applies in, diff
    ("ckb-cli", "ckb-cli", "https://github.com/nervosnetwork/ckb-cli", "80efc21c30e9fc7847407a217034681b6e46c763",
     "src", "X6/ckb-cli/patch.diff"),
    ("CCC", "ccc", "https://github.com/ckb-devrel/ccc", "7095ccad564b94ea2e59284cb4a364aa3499252e",
     "packages/core/src", "X6/ccc/patch.diff"),
    ("Neuron", "neuron", "https://github.com/nervosnetwork/neuron", "d3a7467d218e4b6f777326682a83fec802669c00",
     "packages/neuron-wallet/src", "X6/neuron/patch.diff"),
]


def sh(*cmd, cwd=None, data=None):
    return subprocess.run(cmd, cwd=cwd, input=data, capture_output=True, check=True).stdout


def checkout(refs, folder, url, commit):
    repo = refs / folder
    if not repo.exists():
        print(f"  cloning {url} into {repo} (network)", flush=True)
        sh("git", "clone", "--quiet", url, str(repo))
    sh("git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}")
    return repo


def pristine(repo, commit, path, into):
    """The source folder `path` at `commit`, extracted so that its own name is the root of `into` ("src")."""
    arch = sh("git", "-C", str(repo), "archive", commit, path)
    sh("tar", "-x", "-C", str(into), "--strip-components", str(path.count("/")), data=arch)
    return into


def apply(diff, cwd):
    subprocess.run(["patch", "-p1", "-s", "--dry-run", "-i", str(diff)], cwd=cwd, check=True)
    subprocess.run(["patch", "-p1", "-s", "-i", str(diff)], cwd=cwd, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--refs", default=str(ROOT / "refs"))
    a = ap.parse_args()
    refs = pathlib.Path(a.refs)
    refs.mkdir(parents=True, exist_ok=True)
    rec = json.loads((EXP / "X6" / "results" / "measure.json").read_text())
    fails = 0
    print(f"{'Wallet':<10} {'Diff':<28} {'Applies':<8} {'Recorded (files, added, removed, code)':<40} Counted")
    for name, folder, url, commit, path, diff in WALLETS:
        repo = checkout(refs, folder, url, commit)
        with tempfile.TemporaryDirectory() as tmp:
            work = pathlib.Path(tmp)
            pristine(repo, commit, path, work)
            apply(EXP / diff, work)
            if name == "ckb-cli":  # XRT-4's creation diff goes on top of X6's
                apply(EXP / "XRT" / "ckb-cli-creation.diff", work)
        v = line_count.count(EXP / diff)
        r = rec[name]
        recd = [r["files_changed"], r["lines_added"], r["lines_removed"], r["code_lines_added"]]
        got = [v["files"], v["added"], v["removed"], v["code"]]
        ok = recd == got
        fails += not ok
        print(f"{name:<10} {diff:<28} {'yes':<8} {str(recd):<40} {got} {'PASS' if ok else 'FAIL'}")
    v = line_count.count(EXP / "XRT" / "ckb-cli-creation.diff")
    ok = [v["added"], v["code"]] == [91, 87]
    fails += not ok
    print(f"{'ckb-cli':<10} {'XRT/ckb-cli-creation.diff':<28} {'yes':<8} {'[91 added, 87 code]':<40} "
          f"[{v['added']} added, {v['code']} code] {'PASS' if ok else 'FAIL'}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
