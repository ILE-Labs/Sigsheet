"""An independent implementation of the CKB pieces X1 needs, written from the specs, standard library only.

- Molecule encoding of the transaction types, from blockchain.mol (RFC 0022 and ckb's util/gen-types).
- ckbhash: blake2b-256 with the personalisation "ckb-default-hash" (RFC 0022).
- The transaction hash: ckbhash of the serialized RawTransaction (RFC 0022).
- The multisig signing message, following c/secp256k1_blake160_multisig_all.c in ckb-system-scripts.
- secp256k1 public key recovery from a 65-byte recoverable signature (r | s | recid), pure Python.

Nothing here comes from any wallet's code. Every rule cites the spec or the lock script.
"""
import hashlib

# ---------------------------------------------------------------- hashing

PERSONAL = b"ckb-default-hash"


def ckbhash(data: bytes) -> bytes:
    return hashlib.blake2b(data, digest_size=32, person=PERSONAL).digest()


def blake160(data: bytes) -> bytes:
    return ckbhash(data)[:20]


def h2b(h: str) -> bytes:
    return bytes.fromhex(h[2:] if h.startswith("0x") else h)


def b2h(b: bytes) -> str:
    return "0x" + b.hex()


# ---------------------------------------------------------------- molecule

def u32(n: int) -> bytes:
    return n.to_bytes(4, "little")


def u64(n: int) -> bytes:
    return n.to_bytes(8, "little")


def mol_bytes(b: bytes) -> bytes:
    """Bytes is fixvec<byte>: a 4-byte item count, then the items."""
    return u32(len(b)) + b


def fixvec(items) -> bytes:
    return u32(len(items)) + b"".join(items)


def dynvec(items) -> bytes:
    """dynvec and table share one layout: total size, one offset per item, then the items."""
    header = 4 + 4 * len(items)
    offsets, cur = [], header
    for it in items:
        offsets.append(cur)
        cur += len(it)
    return u32(cur) + b"".join(u32(o) for o in offsets) + b"".join(items)


table = dynvec

HASH_TYPES = {"data": 0, "type": 1, "data1": 2, "data2": 4}


def script(s) -> bytes:
    """Script table: code_hash Byte32, hash_type byte, args Bytes."""
    return table([h2b(s["code_hash"]), bytes([HASH_TYPES[s["hash_type"]]]), mol_bytes(h2b(s["args"]))])


def script_hash(s) -> bytes:
    return ckbhash(script(s))


def out_point(o) -> bytes:
    return h2b(o["tx_hash"]) + u32(int(o["index"], 16))


def cell_input(i) -> bytes:
    return u64(int(i["since"], 16)) + out_point(i["previous_output"])


def cell_output(o) -> bytes:
    t = o.get("type")
    return table([u64(int(o["capacity"], 16)), script(o["lock"]), script(t) if t else b""])


DEP_TYPES = {"code": 0, "dep_group": 1}


def cell_dep(d) -> bytes:
    return out_point(d["out_point"]) + bytes([DEP_TYPES[d["dep_type"]]])


def raw_transaction(tx) -> bytes:
    """RawTransaction table, with the fields in RFC 0022 order. tx uses the RPC (snake_case, hex) form."""
    return table([
        u32(int(tx["version"], 16)),
        fixvec([cell_dep(d) for d in tx["cell_deps"]]),
        fixvec([h2b(h) for h in tx["header_deps"]]),
        fixvec([cell_input(i) for i in tx["inputs"]]),
        dynvec([cell_output(o) for o in tx["outputs"]]),
        dynvec([mol_bytes(h2b(d)) for d in tx["outputs_data"]]),
    ])


def tx_hash(tx) -> bytes:
    return ckbhash(raw_transaction(tx))


def witness_args(lock=None, input_type=None, output_type=None) -> bytes:
    """WitnessArgs table of three BytesOpt fields; an absent field is zero bytes long."""
    opt = lambda b: b"" if b is None else mol_bytes(b)
    return table([opt(lock), opt(input_type), opt(output_type)])


def parse_witness_args(w: bytes):
    """Return (lock, input_type, output_type) or raise ValueError if w isn't a valid WitnessArgs."""
    if len(w) < 4:
        raise ValueError("too short")
    total = int.from_bytes(w[:4], "little")
    if total != len(w):
        raise ValueError("size field doesn't match")
    if total == 4:
        raise ValueError("WitnessArgs has 3 fields")
    first = int.from_bytes(w[4:8], "little")
    if first % 4 or first < 8:
        raise ValueError("bad header")
    count = first // 4 - 1
    if count < 3:
        raise ValueError("WitnessArgs has 3 fields")
    offs = [int.from_bytes(w[4 + 4 * i: 8 + 4 * i], "little") for i in range(count)] + [total]
    fields = []
    for i in range(3):
        seg = w[offs[i]:offs[i + 1]]
        if not seg:
            fields.append(None)
        else:
            n = int.from_bytes(seg[:4], "little")
            if n + 4 != len(seg):
                raise ValueError("bad Bytes field")
            fields.append(seg[4:])
    return tuple(fields)


# ---------------------------------------------------------------- multisig

def multisig_script(require_first_n: int, threshold: int, key_hashes) -> bytes:
    """S | R | M | N | key hashes (secp256k1_blake160_multisig_all.c, header comment)."""
    return bytes([0, require_first_n, threshold, len(key_hashes)]) + b"".join(key_hashes)


def parse_multisig_script(b: bytes):
    s, r, m, n = b[0], b[1], b[2], b[3]
    keys = [b[4 + 20 * i: 24 + 20 * i] for i in range(n)]
    return {"reserved": s, "require_first_n": r, "threshold": m, "keys": keys}


def multisig_message(tx, group_indices, witnesses) -> bytes:
    """The signing message the multisig lock checks (secp256k1_blake160_multisig_all.c, main()).

    tx: the transaction in RPC form (for the hash); group_indices: the input indices whose lock is
    this multisig lock, in order; witnesses: the witness bytes, one per index.
    The first group witness is a WitnessArgs whose lock is multisig_script | M * 65 bytes; the
    signature bytes are zeroed before hashing. Every hashed witness is preceded by its length
    as a little-endian u64. Witnesses at indices >= the number of inputs are hashed too.
    """
    first = witnesses[group_indices[0]]
    lock, input_type, output_type = parse_witness_args(first)
    info = parse_multisig_script(lock)
    script_len = 4 + 20 * len(info["keys"])
    if len(lock) != script_len + 65 * info["threshold"]:
        raise ValueError(f"lock is {len(lock)} bytes; the script requires {script_len} + 65 * M")
    zeroed = witness_args(lock[:script_len] + bytes(65 * info["threshold"]), input_type, output_type)
    # The C code zeroes the bytes in place, so the result must equal the original layout.
    assert len(zeroed) == len(first)
    h = hashlib.blake2b(digest_size=32, person=PERSONAL)
    h.update(tx_hash(tx))
    h.update(u64(len(zeroed)))
    h.update(zeroed)
    for i in group_indices[1:]:
        # ckb_load_witness(..., CKB_SOURCE_GROUP_INPUT) returns INDEX_OUT_OF_BOUND when the
        # group input has no witness at its index, and the C loop stops there.
        if i >= len(witnesses):
            break
        h.update(u64(len(witnesses[i])))
        h.update(witnesses[i])
    for i in range(len(tx["inputs"]), len(witnesses)):
        h.update(u64(len(witnesses[i])))
        h.update(witnesses[i])
    return h.digest()


def zeroed_first_witness(first: bytes) -> bytes:
    lock, input_type, output_type = parse_witness_args(first)
    info = parse_multisig_script(lock)
    script_len = 4 + 20 * len(info["keys"])
    return witness_args(lock[:script_len] + bytes(65 * info["threshold"]), input_type, output_type)


# ---------------------------------------------------------------- secp256k1 (pure Python)

P = 2**256 - 2**32 - 977
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        lam = 3 * x1 * x1 * pow(2 * y1, -1, P) % P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)


def _mul(k, pt):
    acc = None
    while k:
        if k & 1:
            acc = _add(acc, pt)
        pt = _add(pt, pt)
        k >>= 1
    return acc


def pubkey_compressed(pt) -> bytes:
    return bytes([2 + (pt[1] & 1)]) + pt[0].to_bytes(32, "big")


def pubkey_from_secret(secret: bytes) -> bytes:
    return pubkey_compressed(_mul(int.from_bytes(secret, "big"), G))


def recover(message: bytes, sig: bytes) -> bytes:
    """Recover the compressed public key from a 65-byte r | s | recid signature over a 32-byte hash."""
    if len(sig) != 65:
        raise ValueError("signature must be 65 bytes")
    r, s, v = int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:64], "big"), sig[64]
    if not (0 < r < N and 0 < s < N) or v > 3:
        raise ValueError("bad signature values")
    x = r + (N if v & 2 else 0)
    if x >= P:
        raise ValueError("bad r")
    y = pow((x * x * x + 7) % P, (P + 1) // 4, P)
    if (y * y - (x * x * x + 7)) % P:
        raise ValueError("r isn't on the curve")
    if (y & 1) != (v & 1):
        y = P - y
    e = int.from_bytes(message, "big")
    rinv = pow(r, -1, N)
    q = _add(_mul(s * rinv % N, (x, y)), _mul((-e * rinv) % N, G))
    if q is None:
        raise ValueError("recovered the point at infinity")
    return pubkey_compressed(q)


def sign(message: bytes, secret: bytes, nonce: bytes = None) -> bytes:
    """Deterministic-enough ECDSA for test keys only (RFC 6979 isn't needed for X1). Low-s form."""
    d = int.from_bytes(secret, "big")
    e = int.from_bytes(message, "big")
    k = int.from_bytes(ckbhash(secret + message + (nonce or b"")), "big") % N or 1
    pt = _mul(k, G)
    r = pt[0] % N
    s = pow(k, -1, N) * (e + r * d) % N
    v = (pt[1] & 1) | (2 if pt[0] >= N else 0)
    if s > N // 2:
        s, v = N - s, v ^ 1
    return r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([v])


# ---------------------------------------------------------------- addresses (RFC 0021, full format, bech32m)

_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _polymod(values):
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if ((top >> i) & 1) else 0
    return chk


def _hrp_expand(hrp):
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _convertbits(data, frombits, tobits, pad=True):
    acc, bits, ret, maxv = 0, 0, [], (1 << tobits) - 1
    for value in data:
        acc = (acc << frombits) | value
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad and bits:
        ret.append((acc << (tobits - bits)) & maxv)
    return ret


def address(s, hrp="ckt") -> str:
    """Full-format address: 0x00 | code_hash | hash_type | args, bech32m (RFC 0021)."""
    payload = b"\x00" + h2b(s["code_hash"]) + bytes([HASH_TYPES[s["hash_type"]]]) + h2b(s["args"])
    data = _convertbits(payload, 8, 5)
    values = _hrp_expand(hrp) + data
    polymod = _polymod(values + [0] * 6) ^ 0x2BC830A3
    checksum = [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_CHARSET[d] for d in data + checksum)


SIGHASH_CODE_HASH = "0x9bd7e06f3ecf4be0f2fcd2188b23f1b9fcc88e5d4b65a8637b17723bbda3cce8"


def sighash_all_message(tx, group_indices, witnesses, zeroed_first: bytes) -> bytes:
    """The message both system locks sign, given the first group witness with its lock already zeroed.

    secp256k1_blake160_sighash_all.c zeroes the 65-byte lock; the multisig lock zeroes the M * 65
    signature bytes after the multisig script. Everything else is the same: tx hash, then each
    hashed witness preceded by its length as a little-endian u64.
    """
    h = hashlib.blake2b(digest_size=32, person=PERSONAL)
    h.update(tx_hash(tx))
    h.update(u64(len(zeroed_first)))
    h.update(zeroed_first)
    for i in group_indices[1:]:
        if i >= len(witnesses):
            break
        h.update(u64(len(witnesses[i])))
        h.update(witnesses[i])
    for i in range(len(tx["inputs"]), len(witnesses)):
        h.update(u64(len(witnesses[i])))
        h.update(witnesses[i])
    return h.digest()


def sighash_zeroed_first_witness(first: bytes) -> bytes:
    _, input_type, output_type = parse_witness_args(first) if first else (None, None, None)
    return witness_args(bytes(65), input_type, output_type)
