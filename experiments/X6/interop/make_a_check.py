#!/usr/bin/env python3
"""Write each X2 case as a path C file (<case>.c.json) and a path A building packet (<case>.a.hex), with the
design-stage prototypes. CCC's path A layer is checked against these (X6 section 4, ccc/harness/a-codec.ts),
and XRT-2's checks read the C files.

Usage, from experiments/X6/interop:  python3 -I -X utf8 make_a_check.py [output folder, default a-check]
R1 and R2 are mainnet cases: they are written only when X2/cases has them (experiments/mainnet-inputs.md).
"""
import json
import pathlib
import sys

EXP = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(EXP / "prototypes"))
import core  # noqa: E402
import fmt_a  # noqa: E402
import fmt_c  # noqa: E402

out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent / "a-check"
out.mkdir(parents=True, exist_ok=True)
for f in sorted((EXP / "X2" / "cases").glob("*.json")):
    m = json.loads(f.read_text())["model"]
    model = core.Model(m["tx"], m["prevs"], m["configs"], m["sigs"])
    (out / f"{f.stem}.c.json").write_bytes(fmt_c.encode(model))
    (out / f"{f.stem}.a.hex").write_text(fmt_a.encode(model).hex())
    print(f.stem)
