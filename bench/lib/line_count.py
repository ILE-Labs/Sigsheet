"""Count a unified diff the way experiments/X6/measure.py counts each wallet's patch.

"Code lines" are added lines that are neither blank nor comment-only (//, /*, *, */ lines).
"""
import re
import sys

COMMENT = re.compile(r"^\s*(//|/\*|\*|\*/)")


def count(path):
    files, cur = {}, None
    added = removed = code = 0
    for line in open(path, encoding="utf-8").read().splitlines():
        if line.startswith("+++ "):
            cur = line[4:].split("\t")[0]
            files.setdefault(cur, 0)
            continue
        if line.startswith("--- "):
            continue
        if cur and line.startswith("+"):
            added += 1
            files[cur] += 1
            if line[1:].strip() and not COMMENT.match(line[1:]):
                code += 1
        elif cur and line.startswith("-"):
            removed += 1
    return {"files": len(files), "added": added, "removed": removed, "code": code}


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, count(p))
