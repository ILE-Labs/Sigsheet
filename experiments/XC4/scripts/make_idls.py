#!/usr/bin/env python3
"""XC4 step 2: write candidate CKB IDL 0.1.0 documents for the multisig witness lock.

Usage, from experiments/XC4:
    python3 -I -X utf8 scripts/make_idls.py

The multisig witness lock is S | R | M | N | N x 20-byte key hashes | M x 65-byte signatures, where the
counts N and M are single bytes at offsets 3 and 2 (background.md section 1). CKB IDL's linear-0.1.0 profile
has no "count taken from an earlier field": a vector carries its own u32 LE element count, `bytes` its own
u32 LE length, and `bytes_fixed_N` a length fixed in the document (ckb-idl-spec ebec169,
encoding/linear-0.1.0.md). So the script writes four kinds of candidate:

  generic.json        the natural description: four uint8 fields, then vector<bytes_fixed_20> and
                      vector<secp256k1_sig>. Expected to be a valid document that fails on real witnesses.
  fixed-2of3.json     one document per (N, M): the counts fixed in the document (2-of-3, then 3-of-5).
  fixed-3of5.json
  union-n<K>.json     a union whose u32 LE tag is the four header bytes read as one little-endian u32
                      (S | R<<8 | M<<16 | N<<24), with one variant per (R, M, N) for every N <= K.
                      Variants per union are capped at 64 (schema/idl-0.1.0.schema.json, limits.md).

Every document is written as RFC 8785 canonical JSON (sorted keys, no whitespace; all values here are
ASCII strings, integers and booleans, for which json.dumps with these options gives the canonical form).
Prints each file's size and variant count.
"""
import json
import pathlib

OUT = pathlib.Path(__file__).resolve().parent.parent / "idl"
U8 = lambda name: {"name": name, "required": True, "type": "uint8"}
SIG = lambda name: {"name": name, "required": True, "type": "secp256k1_sig", "wire_type": "bytes_fixed_65"}
HEADER = [U8("s"), U8("require_first_n"), U8("threshold"), U8("pubkeys_cnt")]


def doc(fields):
    return {"idl_version": "0.1.0", "interfaces": [{"encoding": {"id": "ckb-idl-linear-0.1.0"},
                                                    "fields": fields, "id": "lock_witness",
                                                    "kind": "witness_args.lock"}]}


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def fixed(m, n):
    return doc(HEADER + [{"name": "key_hashes", "required": True, "type": f"bytes_fixed_{20 * n}"}]
               + [SIG(f"signature_{i}") for i in range(1, m + 1)])


def union(max_n):
    variants = []
    for n in range(1, max_n + 1):
        for m in range(1, n + 1):
            for r in range(0, m + 1):
                tag = 0 | (r << 8) | (m << 16) | (n << 24)
                variants.append({"tag": tag, "name": f"r{r}_m{m}_n{n}",
                                 "fields": [{"name": "key_hashes", "required": True,
                                             "type": f"bytes_fixed_{20 * n}"}]
                                 + [SIG(f"signature_{i}") for i in range(1, m + 1)]})
    variants.sort(key=lambda v: v["tag"])
    return doc([{"name": "header_and_config", "required": True, "type": "union", "variants": variants}]), len(variants)


def main():
    OUT.mkdir(exist_ok=True)
    generic = doc(HEADER + [{"items": {"type": "bytes_fixed_20"}, "name": "key_hashes", "required": True, "type": "vector"},
                            {"items": {"type": "secp256k1_sig", "wire_type": "bytes_fixed_65"}, "name": "signatures",
                             "required": True, "type": "vector"}])
    docs = {"generic.json": (generic, 0), "fixed-2of3.json": (fixed(2, 3), 0), "fixed-3of5.json": (fixed(3, 5), 0)}
    for k in (3, 5, 6):
        docs[f"union-n{k}.json"] = union(k)
    for name, (d, variants) in docs.items():
        data = canonical(d)
        (OUT / name).write_bytes(data)
        fields = data.count(b'"required"')
        print(f"{name:18} {len(data):>7} bytes  {variants:>3} union variants  {fields:>4} field entries")


if __name__ == "__main__":
    main()
