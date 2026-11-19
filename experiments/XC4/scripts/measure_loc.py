#!/usr/bin/env python3
"""XC4 step 5: implementation size, counted in lines at the pinned commits (refs-manifest.md).

Usage, from experiments/XC4:
    python3 -I -X utf8 scripts/measure_loc.py > results/loc.json

Counts (a) the CKB IDL 0.1.0 Rust client that a wallet would add to decode a witness through an IDL,
excluding its #[cfg(test)] modules; (b) the code each wallet already has for the multisig witness lock
layout, found by reading the files: the span from the first to the last line of each named block.
"Code lines" leaves out blank lines and lines that are only comments.
"""
import json
import pathlib
import re

REFS = pathlib.Path(__file__).resolve().parents[3] / "refs"


def code_lines(lines, lang):
    n = 0
    for l in lines:
        s = l.strip()
        if not s or s.startswith("//") or (lang == "rs" and s.startswith("///")) or s.startswith("*") or s.startswith("/*"):
            continue
        n += 1
    return n


def span(path, start_pat, end_line_pat, lang):
    lines = (REFS / path).read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if re.search(start_pat, l))
    end = next(i for i in range(start + 1, len(lines)) if re.match(end_line_pat, lines[i]))
    body = lines[start:end + 1]
    return {"file": path, "lines": f"L{start + 1}-L{end + 1}", "total_lines": len(body), "code_lines": code_lines(body, lang)}


out = {"ckb_idl_client_e7d8124": {}, "existing_multisig_witness_code": {}}
total = code = 0
for f in sorted((REFS / "ckb-idl/ckb-idl-client/src").glob("*.rs")):
    lines = f.read_text().splitlines()
    cut = next((i for i, l in enumerate(lines) if l.strip() == "#[cfg(test)]"), len(lines))
    body = lines[:cut]
    out["ckb_idl_client_e7d8124"][f.name] = {"lines_before_tests": len(body), "code_lines": code_lines(body, "rs")}
    total += len(body)
    code += code_lines(body, "rs")
out["ckb_idl_client_e7d8124"]["TOTAL"] = {"lines_before_tests": total, "code_lines": code}

w = out["existing_multisig_witness_code"]
# ckb-sdk 5.0.0 (ckb-cli 2.0.0 builds with it): struct MultisigConfig and its impl block.
w["ckb-sdk-rust MultisigConfig struct"] = span("ckb-sdk-rust/src/unlock/signer.rs", r"^pub struct MultisigConfig", r"^}", "rs")
w["ckb-sdk-rust MultisigConfig impl"] = span("ckb-sdk-rust/src/unlock/signer.rs", r"^impl MultisigConfig", r"^}", "rs")
# CCC 1.23.1: the MultisigCkbWitness type, codec and class.
w["ccc MultisigCkbWitnessLike type"] = span("ccc/packages/core/src/signer/ckb/signerMultisigCkbReadonly.ts", r"^export type MultisigCkbWitnessLike", r"^\};?\s*$", "ts")
w["ccc MultisigCkbWitness codec decorator"] = span("ccc/packages/core/src/signer/ckb/signerMultisigCkbReadonly.ts", r"^@codec\(", r"^\}\)", "ts")
w["ccc MultisigCkbWitness class"] = span("ccc/packages/core/src/signer/ckb/signerMultisigCkbReadonly.ts", r"^export class MultisigCkbWitness", r"^\}", "ts")
# Neuron v0.204.1: the multisig script serializer.
w["neuron Multisig.serialize"] = span("neuron/packages/neuron-wallet/src/models/multisig.ts", r"static serialize\(", r"^  \}", "ts")
print(json.dumps(out, indent=1))
