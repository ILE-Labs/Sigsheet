"""secp256k1: public key recovery, low-s, the high-s twin, and signing for authoring only.

Constants and recovery follow nervosnetwork/secp256k1 at 3ffde18, the library the system locks build with
(https://github.com/nervosnetwork/secp256k1/blob/3ffde18a060aaf4df5b81e7d88355f1e99874650/src/modules/recovery/main_impl.h#L38-L121):
a 65-byte signature is r || s || recovery id, big-endian; r and s must be non-zero and below the order N; the id is
0 to 3; bit 1 of the id adds N to x (only while x stays below p), bit 0 is the parity of y; the key is
r^-1 (s R - e G). The locks compare blake160 of the 33-byte compressed key.

`sign` is used only by the one-time authoring of new vector signatures; building and checking the vectors never sign.
"""

import functools
import secrets

# Field prime, group order, half order and generator: src/field_5x52_impl.h L23, src/scalar_4x64_impl.h L11-L25,
# src/group_impl.h L60-L71 at the commit above. The curve is y^2 = x^3 + 7.
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
HALF_N = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0
GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
CURVE_B = 7

_INFINITY = (0, 1, 0)


class InvalidSignature(ValueError):
    """65 bytes from which no public key can be recovered."""


def _double(p):
    x, y, z = p
    if z == 0 or y == 0:
        return _INFINITY
    yy = y * y % P
    s = 4 * x * yy % P
    m = 3 * x * x % P
    x3 = (m * m - 2 * s) % P
    return x3, (m * (s - x3) - 8 * yy * yy) % P, 2 * y * z % P


def _add(p, q):
    if p[2] == 0:
        return q
    if q[2] == 0:
        return p
    x1, y1, z1 = p
    x2, y2, z2 = q
    z1z1, z2z2 = z1 * z1 % P, z2 * z2 % P
    u1, u2 = x1 * z2z2 % P, x2 * z1z1 % P
    s1, s2 = y1 * z2 * z2z2 % P, y2 * z1 * z1z1 % P
    if u1 == u2:
        return _double(p) if s1 == s2 else _INFINITY
    h, r = (u2 - u1) % P, (s2 - s1) % P
    hh = h * h % P
    hhh = h * hh % P
    x3 = (r * r - hhh - 2 * u1 * hh) % P
    return x3, (r * (u1 * hh - x3) - s1 * hhh) % P, h * z1 * z2 % P


def _combine(a: int, p, b: int, q):
    """a P + b Q, by one joint double-and-add."""
    pq = _add(p, q)
    acc = _INFINITY
    for i in range(max(a.bit_length(), b.bit_length()) - 1, -1, -1):
        acc = _double(acc)
        bits = (a >> i & 1, b >> i & 1)
        if bits == (1, 1):
            acc = _add(acc, pq)
        elif bits == (1, 0):
            acc = _add(acc, p)
        elif bits == (0, 1):
            acc = _add(acc, q)
    return acc


def _affine(p) -> tuple[int, int] | None:
    x, y, z = p
    if z == 0:
        return None
    zi = pow(z, -1, P)
    zi2 = zi * zi % P
    return x * zi2 % P, y * zi2 * zi % P


def _compressed(point: tuple[int, int]) -> bytes:
    x, y = point
    return bytes([2 + (y & 1)]) + x.to_bytes(32, "big")


def _lift(x: int, odd: int):
    y2 = (x * x * x + CURVE_B) % P
    y = pow(y2, (P + 1) // 4, P)
    if y * y % P != y2:
        return None
    if y & 1 != odd:
        y = P - y
    return x, y, 1


@functools.cache
def recover(message: bytes, signature: bytes) -> bytes:
    """The 33-byte compressed public key that made `signature` over the 32-byte `message`."""
    if len(message) != 32 or len(signature) != 65:
        raise InvalidSignature("a message is 32 bytes and a signature 65")
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:64], "big")
    recid = signature[64]
    if recid > 3 or not 0 < r < N or not 0 < s < N:
        raise InvalidSignature("r, s or the recovery id is out of range")
    x = r
    if recid & 2:
        if r >= P - N:
            raise InvalidSignature("r + N isn't below p")
        x = r + N
    point = _lift(x, recid & 1)
    if point is None:
        raise InvalidSignature("r isn't the x of a curve point")
    e = int.from_bytes(message, "big") % N
    r_inv = pow(r, -1, N)
    q = _affine(_combine(r_inv * s % N, point, -r_inv * e % N, (GX, GY, 1)))
    if q is None:
        raise InvalidSignature("the recovered point is at infinity")
    return _compressed(q)


def is_low_s(signature: bytes) -> bool:
    return int.from_bytes(signature[32:64], "big") <= HALF_N


def high_s_twin(signature: bytes) -> bytes:
    """s -> N - s with the parity bit of the recovery id flipped: the same key over the same message."""
    s = int.from_bytes(signature[32:64], "big")
    return signature[:32] + (N - s).to_bytes(32, "big") + bytes([signature[64] ^ 1])


def normalize_low_s(signature: bytes) -> bytes:
    return signature if is_low_s(signature) else high_s_twin(signature)


def public_key(secret: bytes) -> bytes:
    d = int.from_bytes(secret, "big")
    if not 0 < d < N:
        raise ValueError("a secret key is a scalar from 1 to N - 1")
    point = _affine(_combine(d, (GX, GY, 1), 0, _INFINITY))
    return _compressed(point)


def sign(message: bytes, secret: bytes) -> bytes:
    """An ECDSA signature with a random nonce, in low-s form. For authoring vectors only."""
    d = int.from_bytes(secret, "big")
    e = int.from_bytes(message, "big") % N
    while True:
        k = secrets.randbelow(N - 1) + 1
        rx, ry = _affine(_combine(k, (GX, GY, 1), 0, _INFINITY))
        r = rx % N
        s = pow(k, -1, N) * (e + r * d) % N
        if r and s:
            break
    recid = (ry & 1) | (2 if rx >= N else 0)
    if s > HALF_N:
        s, recid = N - s, recid ^ 1
    return r.to_bytes(32, "big") + s.to_bytes(32, "big") + bytes([recid])
