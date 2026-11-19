# The vector generator

Builds every test vector in `vectors/` from its recorded input, by the rules of the specification (`spec/sigsheet.md`),
and checks them. Python 3 (3.14.4 in CI), standard library only. It is separate from every implementation: it imports
no wallet code, and nothing in the repository imports it.

## Commands

From the repository root (or from this folder, without `PYTHONPATH`):

| Command | Reads | Writes |
|---|---|---|
| `PYTHONPATH=generator python -m sigsheet_vectors build` | every `input.json` in `vectors/`, `vectors/mainnet/` | every other file in `vectors/`, and `vectors/index.json` |
| `PYTHONPATH=generator python -m sigsheet_vectors check` | the same | nothing; it rebuilds in memory, compares every byte with `vectors/` and fails on any difference, missing file or unexpected file |
| `PYTHONPATH=generator python -m sigsheet_vectors fetch-mainnet [--rpc URL]` | CKB mainnet JSON-RPC (`https://mainnet.ckb.dev/` by default) and GitHub, read-only; `vectors/mainnet/` | only `vectors/mainnet/.fetched/` |
| `PYTHONPATH=generator python -m sigsheet_vectors.author` | `vectors/` | the `input.json` of any synthetic case or attack that doesn't have one yet; never one that exists |

`build` and `check` use no randomness, clock, network or environment variable, so they give the same bytes on every
run. `fetch-mainnet` checks every transaction hash it fetches and the SHA-256 of every GitHub file
(`vectors/mainnet/inputs.sha256`), rebuilds R1 and R2, and compares each rebuilt file's SHA-256 and the cases' messages,
unsigned ids and final transaction hashes with `vectors/mainnet/<id>/expected.json`. A file it has already fetched is
used again when its digest or hash checks, so a second run needs no network.

`author.py` made the inputs no recording holds, once: new signatures with keys made in memory from `secrets` and
dropped, and the attacks' random bytes. Only key hashes and signatures are written. `build` never calls it.

## Tests

```sh
PYTHONPATH=generator python -m unittest discover -s generator/tests
ruff format --check --config generator/ruff.toml generator check/locks
ruff check --config generator/ruff.toml generator check/locks
```

One test file per module, and `test_rebuild.py`, which runs `check` on the committed vectors. The merge test merges
every case's partial files in 200 random orders and groupings, with a fixed seed. ruff 0.17.4 is a development tool
only (`pip install ruff==0.17.4`).

## Layout

| Module | Responsibility |
|---|---|
| `sigsheet_vectors/__main__.py` | The command line |
| `ckb/hashing.py` | ckbhash and blake160 |
| `ckb/molecule.py` | The CKB types, their Molecule encoding and hashes, and strict decoding |
| `ckb/rpc_json.py` | CKB RPC JSON to and from the CKB types, with the hex rules |
| `ckb/secp256k1.py` | Public key recovery, low-s and the high-s twin; signing for `author.py` only |
| `ckb/merkle.py` | CBMT roots and transaction-proof verification |
| `ckb/dao.py` | Nervos DAO cells, the deposit header index, the maximum withdraw and the minimal since |
| `ckb/scripts.py` | The lock kinds version 1 signs, the known tokens, the cell deps of each network |
| `ckb/addresses.py` | Full-format addresses |
| `sigsheet/canonical.py` | RFC 8785 for the Sigsheet domain, and the canonical check |
| `sigsheet/schema.py` | The seven top-level fields and their shapes |
| `sigsheet/check_ids.py` | Every check id and drop-reason id, in the specification's order |
| `sigsheet/reader.py` | Every reader check, in order; the accepted file with its groups and unsigned id |
| `sigsheet/messages.py` | Each lock kind's message rule |
| `sigsheet/signatures.py` | Verification: membership first, recovery, low-s |
| `sigsheet/merge.py` | The merge rule |
| `sigsheet/finalize.py` | Ready and finalize, the genesis rule, partial finalize |
| `sigsheet/fee.py` | The fee: exact, from inclusion proofs, or an upper bound |
| `sigsheet/show.py` | What a signer is shown |
| `sigsheet/create.py` | Creating a file from a node's recorded answers |
| `vectors/cases.py` | The case vectors and how each is built from its input |
| `vectors/attacks.py` | The attack vectors, each with its declared result, and their changes |
| `vectors/writer.py` | Writes `vectors/` and `index.json`, and compares a rebuild with them |
| `mainnet/fetch.py` | The read-only fetch of R1 and R2 |
| `author.py` | One-time authoring of the inputs no recording holds |
