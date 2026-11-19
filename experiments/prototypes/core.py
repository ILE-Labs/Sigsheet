"""Shared core of the throwaway design-stage prototypes (paths C, B and A). Standard library only.

Not a spec and not a reference implementation: experiment code that the X2-X7 experiments run.

The internal model every prototype encodes and decodes (one per unsigned transaction):
- tx:      the transaction in CKB RPC JSON (snake_case, hex numbers). Its witnesses are *templates*: the first
           witness of every lock group that a Sigsheet file signs (multisig or single-key) has its lock field
           absent (WitnessArgs with lock = None, or "0x"); input_type, output_type, the group's other witnesses
           and every witness beyond the inputs are kept as they are, because the lock's message covers them
           (background.md section 1).
- prevs:   {tx_hash: raw previous transaction in RPC JSON, without witnesses}. Raw only is enough to prove an
           input cell, since the hash covers the raw transaction (background.md section 2; X2a).
- configs: {blake160(multisig script) as hex: {"r", "m", "keys": [20-byte key hashes]}}; one entry per multisig
           script, bound by hash to the lock args' first 20 bytes (background.md section 1).
- sigs:    {lock script hash: {signer key hash: 65-byte signature}}, every verified signature, normalized to
           low-s, kept beyond M until finalizing (design-record.md, decision D11).

The rules implemented here apply to every format (design-record.md, decisions D8, D11 and D12):
- the lock kind is read from the input cell (its code hash and hash type), never from a declared field;
- merge = union of verified member signatures keyed by signer, normalized to low-s, the smaller bytes on a
  conflict; files must describe the same unsigned transaction (same transaction and witness templates);
- finalize = the first R members, then the lowest member indices up to M, written in member order.
"""
import copy
import hashlib
import pathlib
import sys

X1 = pathlib.Path(__file__).resolve().parent.parent / "X1" / "scripts"
sys.path.insert(0, str(X1))
import ckbcore as c  # noqa: E402  (X1's independent implementation: Molecule, hashes, secp256k1)

# ------------------------------------------------------------------ lock kinds, from the input cell

SIGHASH = ("0x9bd7e06f3ecf4be0f2fcd2188b23f1b9fcc88e5d4b65a8637b17723bbda3cce8", "type")
MULTISIG_DEPLOYMENTS = {
    ("0x5c5069eb0857efc65e1bca0c07df34c31663b3622fd3876c876320fc9634e2a8", "type"): "genesis",
    ("0xd1a9f877aed3f5e07cb9c52b61ab96d06f250ae6883cc7f0a2423db0976fc821", "type"): "2024",
    ("0x765b3ed6ae264b335d07e73ac332bf2c0f38f8d3340ed521cb447b4c42dd5f09", "type"): "2024-testnet",
    ("0x6283a479a3cf5d4276cd93594de9f1827ab9b55c7b05b3d28e4c2e0a696cfefd", "type"): "2024-devnet",
    ("0x36c971b8d41fbd94aabca77dc75e826729ac98447b46f91e00796155dddb0d29", "data1"): "v2",
}
# background.md section 3 (mainnet and testnet); the devnet's 2024 type hash is X1's (data/devnet/genesis-info.json).


def lock_kind(lock):
    key = (lock["code_hash"], lock["hash_type"])
    if key == SIGHASH:
        return "sighash"
    if key in MULTISIG_DEPLOYMENTS:
        return "multisig"
    return "unknown"


class SigsheetError(Exception):
    """A file that a reader must refuse (not merely a signature to drop)."""


# ------------------------------------------------------------------ small helpers

N_HALF = c.N // 2
RAW_FIELDS = ("version", "cell_deps", "header_deps", "inputs", "outputs", "outputs_data")


def raw_of(tx):
    return {k: tx[k] for k in RAW_FIELDS}


def low_s(sig: bytes) -> bytes:
    """Normalize a 65-byte r|s|v signature to low-s (s <= N/2), flipping the recovery bit. Same key, same message."""
    s = int.from_bytes(sig[32:64], "big")
    if s > N_HALF:
        return sig[:32] + (c.N - s).to_bytes(32, "big") + bytes([sig[64] ^ 1])
    return sig


def malleate(sig: bytes) -> bytes:
    """The high-s twin of a signature (s -> N - s, recovery bit flipped): valid for the same key and message."""
    s = int.from_bytes(sig[32:64], "big")
    return sig[:32] + (c.N - s).to_bytes(32, "big") + bytes([sig[64] ^ 1])


def script_of(cfg) -> bytes:
    return c.multisig_script(cfg["r"], cfg["m"], [c.h2b(k) for k in cfg["keys"]])


def config_id(cfg) -> str:
    return c.b2h(c.blake160(script_of(cfg)))


def check_config(cfg):
    n = len(cfg["keys"])
    if not (0 < n <= 255 and 0 < cfg["m"] <= n and 0 <= cfg["r"] <= cfg["m"]):
        raise SigsheetError(f"invalid multisig config R={cfg['r']} M={cfg['m']} N={n}")
    if len(set(cfg["keys"])) != n:
        raise SigsheetError("duplicate member key hash")


# ------------------------------------------------------------------ the model

class Model:
    def __init__(self, tx, prevs, configs, sigs):
        self.tx = tx
        self.prevs = prevs
        self.configs = configs
        self.sigs = sigs

    def copy(self):
        return Model(copy.deepcopy(self.tx), copy.deepcopy(self.prevs), copy.deepcopy(self.configs),
                     copy.deepcopy(self.sigs))

    def key(self):
        """Everything, for equality tests."""
        return (canon(self.tx), canon(self.prevs), canon(self.configs), canon(self.sigs))

    def __eq__(self, other):
        return isinstance(other, Model) and self.key() == other.key()

    def unsigned_id(self) -> str:
        """Identity of the unsigned transaction: hash of the raw transaction and the witness templates."""
        h = hashlib.blake2b(digest_size=32, person=c.PERSONAL)
        h.update(c.tx_hash(self.tx))
        for w in self.tx["witnesses"]:
            b = c.h2b(w)
            h.update(c.u64(len(b)) + b)
        return c.b2h(h.digest())


def canon(obj) -> str:
    """Compact JSON with sorted keys: equal to RFC 8785 for the value domain used here (ASCII strings, integers)."""
    import json
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ------------------------------------------------------------------ resolving inputs and groups

def spent_output(model, i):
    """The output input i spends, from the carried previous transaction (checked by hash)."""
    op = model.tx["inputs"][i]["previous_output"]
    prev = model.prevs.get(op["tx_hash"])
    if prev is None:
        raise SigsheetError(f"input {i}: previous transaction {op['tx_hash'][:12]}... not in the file")
    if c.b2h(c.tx_hash(prev)) != op["tx_hash"]:
        raise SigsheetError(f"input {i}: previous transaction doesn't hash to its out point")
    idx = int(op["index"], 16)
    if idx >= len(prev["outputs"]):
        raise SigsheetError(f"input {i}: out point index {idx} beyond the previous transaction's outputs")
    return prev["outputs"][idx], prev["outputs_data"][idx]


def lock_groups(model):
    """{lock script hash: {"lock", "kind", "inputs": [indices]}} in order of first input."""
    groups = {}
    for i in range(len(model.tx["inputs"])):
        out, _ = spent_output(model, i)
        lh = c.b2h(c.script_hash(out["lock"]))
        g = groups.setdefault(lh, {"lock": out["lock"], "kind": lock_kind(out["lock"]), "inputs": []})
        g["inputs"].append(i)
    return groups


def group_config(model, group):
    """The multisig config of a group: found by the args' first 20 bytes, checked by hash; since from the args."""
    args = c.h2b(group["lock"]["args"])
    if len(args) not in (20, 28):
        raise SigsheetError(f"multisig args are {len(args)} bytes; the lock allows 20 or 28")
    cid = c.b2h(args[:20])
    cfg = model.configs.get(cid)
    if cfg is None:
        raise SigsheetError(f"no multisig config for {cid}")
    check_config(cfg)
    if config_id(cfg) != cid:
        raise SigsheetError(f"multisig config {cid} doesn't hash to its key")
    return cfg


def check_since(model, group):
    """The since rule the v2 lock checks when the args carry a since (background.md section 1); a signer's check."""
    args = c.h2b(group["lock"]["args"])
    if len(args) != 28:
        return None
    want = int.from_bytes(args[20:], "little")
    for i in group["inputs"]:
        have = int(model.tx["inputs"][i]["since"], 16)
        flags_w, flags_h = want >> 56, have >> 56
        if flags_w != flags_h or (have & ((1 << 56) - 1)) < (want & ((1 << 56) - 1)):
            return f"input {i} since {hex(have)} doesn't satisfy the args' since {hex(want)}"
    return None


# ------------------------------------------------------------------ messages

def template_parts(model, group, strict=True):
    """input_type and output_type of the group's first witness. strict: the lock field must be absent (a
    template); otherwise a present lock is ignored, as the message zeroes it anyway."""
    w = model.tx["witnesses"]
    first = group["inputs"][0]
    if first >= len(w):
        raise SigsheetError(f"group's first input {first} has no witness template")
    b = c.h2b(w[first])
    lock, it, ot = (None, None, None) if b == b"" else c.parse_witness_args(b)
    if strict and lock is not None:
        raise SigsheetError(f"witness {first}: a template's lock field must be absent")
    return it, ot


def zeroed_lock(model, group):
    if group["kind"] == "multisig":
        cfg = group_config(model, group)
        return script_of(cfg) + bytes(65 * cfg["m"])
    if group["kind"] == "sighash":
        return bytes(65)
    raise SigsheetError(f"lock kind {group['kind']} isn't one Sigsheet v1 signs")


def group_message(model, group) -> bytes:
    """The signing message of the multisig lock (and of the single-key lock, the same rule with a 65-byte lock):
    secp256k1_blake160_multisig_all.c L205-L281 (background.md section 1), computed from the file alone."""
    it, ot = template_parts(model, group, strict=False)
    first = c.witness_args(zeroed_lock(model, group), it, ot)
    w = [c.h2b(x) for x in model.tx["witnesses"]]
    h = hashlib.blake2b(digest_size=32, person=c.PERSONAL)
    h.update(c.tx_hash(model.tx))
    h.update(c.u64(len(first)) + first)
    for i in group["inputs"][1:]:
        if i >= len(w):
            break
        h.update(c.u64(len(w[i])) + w[i])
    for i in range(len(model.tx["inputs"]), len(w)):
        h.update(c.u64(len(w[i])) + w[i])
    return h.digest()


# ------------------------------------------------------------------ signatures

def signer_of(model, group, sig: bytes, msg: bytes = None):
    """The key hash a signature belongs to, if it is a valid signature over the group's message by a member
    (multisig) or by the args' key (single-key); else None."""
    if len(sig) != 65:
        return None
    msg = msg or group_message(model, group)
    try:
        kh = c.b2h(c.blake160(c.recover(msg, sig)))
    except ValueError:
        return None
    if group["kind"] == "multisig":
        return kh if kh in group_config(model, group)["keys"] else None
    if group["kind"] == "sighash":
        return kh if kh == group["lock"]["args"] else None
    return None


def sign_group(model, group_hash, secret_hex):
    """Add one signature with a test key (the prototypes' own signer)."""
    groups = lock_groups(model)
    g = groups[group_hash]
    msg = group_message(model, g)
    sig = c.sign(msg, c.h2b(secret_hex))
    kh = signer_of(model, g, sig, msg)
    if kh is None:
        raise SigsheetError("this key isn't a member of the group")
    add_sig(model.sigs, group_hash, kh, sig)
    return kh


def add_sig(sigs, group_hash, kh, sig):
    s = low_s(sig)
    cur = sigs.setdefault(group_hash, {}).get(kh)
    if cur is None or c.h2b(cur) > s:
        sigs[group_hash][kh] = c.b2h(s)


def verified_sigs(model):
    """Every signature in the file that verifies, normalized; and the list of dropped entries with reasons."""
    groups = lock_groups(model)
    out, dropped = {}, []
    for gh, entries in sorted(model.sigs.items()):
        g = groups.get(gh)
        if g is None:
            dropped += [(gh, k, "no input of the transaction has this lock") for k in entries]
            continue
        if g["kind"] == "unknown":
            dropped += [(gh, k, "lock kind not signed by Sigsheet v1") for k in entries]
            continue
        msg = group_message(model, g)
        for kh, sig in sorted(entries.items()):
            who = signer_of(model, g, c.h2b(sig), msg)
            if who is None:
                dropped.append((gh, kh, "doesn't verify against the group's message, or not a member"))
            elif who != kh:
                dropped.append((gh, kh, f"signed by {who}, not by the key it's filed under"))
            else:
                add_sig(out, gh, kh, c.h2b(sig))
    return out, dropped


# ------------------------------------------------------------------ validation, merge, finalize

def validate(model):
    """What a reader checks before trusting a file. Raises SigsheetError for a file it must refuse; returns
    warnings (dropped signatures, since problems) otherwise."""
    tx = model.tx
    if len(tx["outputs"]) != len(tx["outputs_data"]):
        raise SigsheetError("outputs and outputs_data differ in length")
    for h, prev in model.prevs.items():
        if c.b2h(c.tx_hash(prev)) != h:
            raise SigsheetError(f"previous transaction {h[:12]}... doesn't hash to its key")
    used = {i["previous_output"]["tx_hash"] for i in tx["inputs"]}
    extra = set(model.prevs) - used
    if extra:
        raise SigsheetError(f"{len(extra)} previous transaction(s) not spent by any input")
    for cid, cfg in model.configs.items():
        check_config(cfg)
        if config_id(cfg) != cid:
            raise SigsheetError(f"multisig config {cid[:12]}... doesn't hash to its key")
    groups = lock_groups(model)
    needed = {c.b2h(c.h2b(g["lock"]["args"])[:20]) for g in groups.values() if g["kind"] == "multisig"}
    if set(model.configs) - needed:
        raise SigsheetError("a multisig config that no input uses")
    warnings = []
    for gh, g in groups.items():
        if g["kind"] in ("multisig", "sighash"):
            it, ot = template_parts(model, g)
            if it is None and ot is None and model.tx["witnesses"][g["inputs"][0]] != "0x":
                raise SigsheetError(f"witness {g['inputs'][0]}: a lock-only template must be written as 0x")
            group_message(model, g)
        if g["kind"] == "multisig":
            w = check_since(model, g)
            if w:
                warnings.append(w)
    _, dropped = verified_sigs(model)
    warnings += [f"dropped signature {k[:12]}... in group {gh[:12]}...: {why}" for gh, k, why in dropped]
    return warnings


def merge(*models):
    """The merge rule: the same unsigned transaction; union of carried context; union of verified signatures."""
    base = models[0]
    uid = base.unsigned_id()
    for m in models[1:]:
        if m.unsigned_id() != uid:
            raise SigsheetError("files describe different unsigned transactions")
    out = Model(copy.deepcopy(base.tx), {}, {}, {})
    for m in models:
        for h, p in m.prevs.items():
            if c.b2h(c.tx_hash(p)) == h:
                out.prevs[h] = copy.deepcopy(p)
        for cid, cfg in m.configs.items():
            try:
                check_config(cfg)
            except SigsheetError:
                continue
            if config_id(cfg) == cid:
                out.configs[cid] = copy.deepcopy(cfg)
    cands = {}
    for m in models:
        for gh, entries in m.sigs.items():
            for kh, sig in entries.items():
                cands.setdefault(gh, []).append((kh, sig))
    groups = lock_groups(out)
    for gh, entries in cands.items():
        g = groups.get(gh)
        if g is None or g["kind"] == "unknown":
            continue
        msg = group_message(out, g)
        for kh, sig in entries:
            b = c.h2b(sig)
            if signer_of(out, g, b, msg) == kh:
                add_sig(out.sigs, gh, kh, b)
    return out


def status(model):
    """Per group: (kind, verified signers, ready?) with the first-R rule."""
    groups = lock_groups(model)
    ver, _ = verified_sigs(model)
    st = {}
    for gh, g in groups.items():
        have = ver.get(gh, {})
        if g["kind"] == "multisig":
            cfg = group_config(model, g)
            idx = sorted(cfg["keys"].index(k) for k in have)
            ready = all(i in idx for i in range(cfg["r"])) and len(idx) >= cfg["m"]
            st[gh] = {"kind": "multisig", "signed": idx, "m": cfg["m"], "r": cfg["r"], "ready": ready}
        elif g["kind"] == "sighash":
            st[gh] = {"kind": "sighash", "signed": list(have), "ready": len(have) == 1}
        else:
            st[gh] = {"kind": "unknown", "ready": False}
    return st


def finalize(model, require_all=True):
    """The final transaction: the finalize rule's selection; every multisig lock at exactly 4 + 20N + 65M bytes."""
    groups = lock_groups(model)
    ver, _ = verified_sigs(model)
    tx = copy.deepcopy(model.tx)
    for gh, g in groups.items():
        have = ver.get(gh, {})
        if g["kind"] == "multisig":
            cfg = group_config(model, g)
            by_index = {cfg["keys"].index(k): c.h2b(s) for k, s in have.items()}
            if any(i not in by_index for i in range(cfg["r"])) or len(by_index) < cfg["m"]:
                if require_all:
                    raise SigsheetError(f"group {gh[:12]}... not ready: needs the first {cfg['r']} and {cfg['m']} in all")
                continue
            pick = list(range(cfg["r"])) + [i for i in sorted(by_index) if i >= cfg["r"]][: cfg["m"] - cfg["r"]]
            lock = script_of(cfg) + b"".join(by_index[i] for i in sorted(pick))
        elif g["kind"] == "sighash":
            if len(have) != 1:
                if require_all:
                    raise SigsheetError(f"single-key group {gh[:12]}... has no signature")
                continue
            lock = c.h2b(next(iter(have.values())))
        else:
            if require_all:
                raise SigsheetError(f"group {gh[:12]}... has a lock kind Sigsheet v1 doesn't sign")
            continue
        it, ot = template_parts(model, g)
        tx["witnesses"][g["inputs"][0]] = c.b2h(c.witness_args(lock, it, ot))
    return tx


def lock_rule_check(final_tx, prevs):
    """Run the multisig lock's own rules on a final transaction, in Python (X1's implementation): exact length,
    script binding, M distinct members, first R. For single-key groups, the key behind the signature."""
    m = Model(final_tx, prevs, {}, {})
    report = {}
    for gh, g in lock_groups(m).items():
        w0 = c.h2b(final_tx["witnesses"][g["inputs"][0]])
        lock, it, ot = c.parse_witness_args(w0)
        if g["kind"] == "multisig":
            info = c.parse_multisig_script(lock)
            n, mm, r = len(info["keys"]), info["threshold"], info["require_first_n"]
            ok = len(lock) == 4 + 20 * n + 65 * mm
            ok &= c.blake160(lock[: 4 + 20 * n]) == c.h2b(g["lock"]["args"])[:20]
            witnesses = [c.h2b(x) for x in final_tx["witnesses"]]
            msg = c.multisig_message(final_tx, g["inputs"], witnesses)
            used = []
            for j in range(mm):
                sig = lock[4 + 20 * n + 65 * j: 4 + 20 * n + 65 * (j + 1)]
                try:
                    kh = c.blake160(c.recover(msg, sig))
                except ValueError:
                    ok = False
                    continue
                if kh in info["keys"]:
                    k = info["keys"].index(kh)
                    if k in used:
                        ok = False
                    used.append(k)
                else:
                    ok = False
            ok &= all(i in used for i in range(r))
            report[gh] = ok
        elif g["kind"] == "sighash":
            zeroed = c.sighash_zeroed_first_witness(w0)
            witnesses = [c.h2b(x) for x in final_tx["witnesses"]]
            msg = c.sighash_all_message(final_tx, g["inputs"], witnesses, zeroed)
            try:
                report[gh] = c.blake160(c.recover(msg, lock)) == c.h2b(g["lock"]["args"])
            except ValueError:
                report[gh] = False
    return report


def template_from_final(tx, groups):
    """The unsigned template of a final (or partly signed) transaction: each signed group's first lock removed."""
    t = copy.deepcopy(tx)
    for g in groups.values():
        if g["kind"] in ("multisig", "sighash"):
            i = g["inputs"][0]
            b = c.h2b(t["witnesses"][i])
            if b:
                _, it, ot = c.parse_witness_args(b)
                t["witnesses"][i] = c.b2h(c.witness_args(None, it, ot)) if (it is not None or ot is not None) else "0x"
    return t
