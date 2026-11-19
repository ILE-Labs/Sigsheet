"""Molecule decoding for the prototypes (encoding comes from X1's ckbcore.py), plus the CKB types in RPC JSON form.

Decoders are strict: every structure must be well formed (sizes and offsets consistent). The callers then check
canonical form by re-encoding and comparing bytes.
"""
from core import c

HASH_TYPE_NAMES = {v: k for k, v in c.HASH_TYPES.items()}
DEP_TYPE_NAMES = {0: "code", 1: "dep_group"}


class MolError(ValueError):
    pass


def u32(b, off=0):
    if len(b) < off + 4:
        raise MolError("short")
    return int.from_bytes(b[off:off + 4], "little")


def table(b, n=None):
    """Fields of a table (or items of a dynvec): total size, offsets, items."""
    if len(b) < 4:
        raise MolError("short header")
    total = u32(b)
    if total != len(b):
        raise MolError(f"size {total} != {len(b)}")
    if total == 4:
        items = []
    else:
        first = u32(b, 4)
        if first % 4 or first < 8 or first > total:
            raise MolError("bad first offset")
        count = first // 4 - 1
        offs = [u32(b, 4 + 4 * i) for i in range(count)] + [total]
        if any(offs[i] > offs[i + 1] for i in range(count)):
            raise MolError("offsets not increasing")
        items = [b[offs[i]:offs[i + 1]] for i in range(count)]
    if n is not None and len(items) != n:
        raise MolError(f"table has {len(items)} fields, expected {n}")
    return items


dynvec = table


def fixvec(b, size):
    n = u32(b)
    if len(b) != 4 + n * size:
        raise MolError("fixvec size")
    return [b[4 + i * size: 4 + (i + 1) * size] for i in range(n)]


def mbytes(b):
    n = u32(b)
    if len(b) != 4 + n:
        raise MolError("Bytes size")
    return b[4:]


def option(b):
    return None if len(b) == 0 else b


# ------------------------------------------------------------------ CKB types <-> RPC JSON

def script(b):
    code_hash, hash_type, args = table(b, 3)
    if len(code_hash) != 32 or len(hash_type) != 1 or hash_type[0] not in HASH_TYPE_NAMES:
        raise MolError("bad Script")
    return {"code_hash": c.b2h(code_hash), "hash_type": HASH_TYPE_NAMES[hash_type[0]], "args": c.b2h(mbytes(args))}


def cell_output(b):
    cap, lock, typ = table(b, 3)
    if len(cap) != 8:
        raise MolError("capacity")
    return {"capacity": hex(int.from_bytes(cap, "little")), "lock": script(lock),
            "type": script(typ) if typ else None}


def out_point(b):
    return {"tx_hash": c.b2h(b[:32]), "index": hex(int.from_bytes(b[32:36], "little"))}


def raw_transaction(b):
    version, deps, hdeps, inputs, outputs, odata = table(b, 6)
    if len(version) != 4:
        raise MolError("version")
    return {
        "version": hex(int.from_bytes(version, "little")),
        "cell_deps": [{"out_point": out_point(d[:36]), "dep_type": DEP_TYPE_NAMES[d[36]]} for d in fixvec(deps, 37)],
        "header_deps": [c.b2h(h) for h in fixvec(hdeps, 32)],
        "inputs": [{"since": hex(int.from_bytes(i[:8], "little")), "previous_output": out_point(i[8:])}
                   for i in fixvec(inputs, 44)],
        "outputs": [cell_output(o) for o in dynvec(outputs)],
        "outputs_data": [c.b2h(mbytes(d)) for d in dynvec(odata)],
    }


def transaction(b):
    raw, wits = table(b, 2)
    tx = raw_transaction(raw)
    tx["witnesses"] = [c.b2h(mbytes(w)) for w in dynvec(wits)]
    return tx


def enc_transaction(tx):
    return c.table([c.raw_transaction(tx), c.dynvec([c.mol_bytes(c.h2b(w)) for w in tx["witnesses"]])])


def enc_bytesvec(items):
    return c.dynvec([c.mol_bytes(x) for x in items])
