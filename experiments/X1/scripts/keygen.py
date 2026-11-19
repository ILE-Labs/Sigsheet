#!/usr/bin/env python3
"""Make fresh secp256k1 test keys for the devnet. Never used anywhere else.

Usage: python3 -I scripts/keygen.py <count> <out.json> [name prefix, default k]
(out goes under keys/ at the repository root, which must be a link to a folder outside the checkout; git ignores it)
Each key: the secret (os.urandom), the compressed public key, its blake160 (the sighash lock args)
and the testnet/devnet ("ckt") sighash address. A copy of each secret is also written as a
one-line hex file next to the JSON, the format ckb-cli's --privkey-path reads.
"""
import json, os, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import ckbcore as c


def keys_outside_checkout(path):
    """Test keys must never be written inside this repository: `keys` at its root must be a link to a folder
    outside it (for example `ln -s "$(mktemp -d)" keys`), which git ignores."""
    root = pathlib.Path(__file__).resolve().parents[3]
    p = pathlib.Path(path).resolve()
    if p == root or root in p.parents:
        raise SystemExit(f"refusing to write a key inside the checkout ({p}); make keys a link to a folder outside "
                         "it: ln -s \"$(mktemp -d)\" keys")
    return path


n, out = int(sys.argv[1]), pathlib.Path(keys_outside_checkout(sys.argv[2]))
prefix = sys.argv[3] if len(sys.argv) > 3 else "k"
keys = []
for i in range(n):
    sec = os.urandom(32)
    pk = c.pubkey_from_secret(sec)
    args = c.b2h(c.blake160(pk))
    keys.append({"name": f"{prefix}{i}", "secret": c.b2h(sec), "pubkey": c.b2h(pk), "blake160": args,
                 "address": c.address({"code_hash": c.SIGHASH_CODE_HASH, "hash_type": "type", "args": args})})
    (out.parent / f"{prefix}{i}.privkey").write_text(c.b2h(sec)[2:] + "\n")
out.write_text(json.dumps(keys, indent=1))
for k in keys:
    print(k["name"], k["blake160"], k["address"])
