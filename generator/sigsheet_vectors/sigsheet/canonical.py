"""RFC 8785 canonical JSON for the Sigsheet value domain, and the canonical check.

The domain: objects with ASCII string keys, arrays, ASCII strings, integers of magnitude below 2^53, true, false
and null. For it, RFC 8785 (https://www.rfc-editor.org/rfc/rfc8785) gives: no whitespace between tokens (3.2.1);
strings with `"` and `\\` escaped, U+0008, U+0009, U+000A, U+000C and U+000D as `\\b \\t \\n \\f \\r`, the other code
points below U+0020 as `\\u00hh` in lowercase, and every other character as it is (3.2.2.2); integers as their decimal
digits, as ECMAScript writes a double that holds them (3.2.2.3); object members sorted by their keys' UTF-16 code
units, which for ASCII keys is code point order (3.2.3). The output is ASCII. Anything outside the domain is refused,
never approximated.
"""

import json

MAX_SAFE_INTEGER = 2**53 - 1
_SHORT_ESCAPES = {0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r", 0x22: '\\"', 0x5C: "\\\\"}


class CanonicalError(ValueError):
    """A value or a file outside the domain (`check_id` "canonical.json"), or not in its canonical form
    ("canonical.form")."""

    def __init__(self, check_id: str, detail: str):
        super().__init__(detail)
        self.check_id = check_id


def _string(s: str, out: list[str]) -> None:
    out.append('"')
    for ch in s:
        c = ord(ch)
        if c > 0x7F:
            raise CanonicalError("canonical.json", "a string with a character outside ASCII")
        if c in _SHORT_ESCAPES:
            out.append(_SHORT_ESCAPES[c])
        elif c < 0x20:
            out.append(f"\\u{c:04x}")
        else:
            out.append(ch)
    out.append('"')


def _value(v, out: list[str]) -> None:
    if v is None:
        out.append("null")
    elif v is True:
        out.append("true")
    elif v is False:
        out.append("false")
    elif type(v) is int:
        if abs(v) > MAX_SAFE_INTEGER:
            raise CanonicalError("canonical.json", "an integer beyond 2^53 - 1")
        out.append(str(v))
    elif type(v) is str:
        _string(v, out)
    elif type(v) is list:
        out.append("[")
        for i, item in enumerate(v):
            if i:
                out.append(",")
            _value(item, out)
        out.append("]")
    elif type(v) is dict:
        if any(type(k) is not str for k in v):
            raise CanonicalError("canonical.json", "an object key that isn't a string")
        out.append("{")
        for i, k in enumerate(sorted(v)):
            if i:
                out.append(",")
            _string(k, out)
            out.append(":")
            _value(v[k], out)
        out.append("}")
    else:
        raise CanonicalError("canonical.json", f"a {type(v).__name__}, outside the domain")


def encode(value) -> bytes:
    out: list[str] = []
    _value(value, out)
    return "".join(out).encode("ascii")


def _no_float(text: str):
    raise CanonicalError("canonical.json", f"a number with a fraction or an exponent: {text}")


def _no_constant(text: str):
    raise CanonicalError("canonical.json", f"{text} isn't JSON")


def _unique(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise CanonicalError("canonical.json", f"the key {k!r} appears twice in one object")
        out[k] = v
    return out


def decode(data: bytes):
    """Parse ASCII JSON in the domain, refusing fractions, exponents, NaN, Infinity and repeated keys."""
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError as e:
        raise CanonicalError("canonical.json", "the bytes aren't ASCII") from e
    try:
        return json.loads(text, parse_float=_no_float, parse_constant=_no_constant, object_pairs_hook=_unique)
    except json.JSONDecodeError as e:
        raise CanonicalError("canonical.json", f"not JSON: {e.msg}") from e


def check(data: bytes):
    """The canonical check: parse, re-encode, and refuse on any byte difference. Returns the parsed value."""
    value = decode(data)
    if encode(value) != data:
        raise CanonicalError("canonical.form", "the bytes differ from the value's canonical encoding")
    return value
