# Sigsheet: one file for a CKB transaction several people sign

- **Status:** draft, version 0.1. Open for review; the text may change before Sigsheet v0.1.0.
- **Format version:** `"0x1"`.
- **Test vectors:** `vectors/` in this repository (informative): every case and attack below as files at their exact
  bytes, with the results a reader must give.

## 1. Introduction

A CKB multisig transaction is signed by several people, often with different tools: ckb-cli, CCC and Neuron each sign
the same lock with their own code. Sigsheet is one canonical JSON file per transaction that carries everything a
signer needs to check what they sign, offline and from the file alone: the transaction, every previous transaction its
inputs spend, the headers and inclusion proofs a Nervos DAO withdrawal needs, the multisig configs, and every
signature so far, keyed by lock group and signer. The file is passed from signer to signer, or each signer posts a
copy and anyone merges the copies; there is no collector role. When enough members have signed, anyone finalizes it
into the transaction to send.

This draft states every rule of the design record (the `research` branch of this repository at commit
`9b22e10f02f70a6dfa71d39791f74c74b1fd5902`, [design record][dr]), including the rules added after its red teams.
Every rule links to its evidence: the design record, an RFC, or a permalink to the code it follows at a pinned commit.

### 1.1 Conventions

- The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT
  RECOMMENDED", "MAY" and "OPTIONAL" in this document are to be interpreted as described in BCP 14 ([RFC 2119][rfc2119],
  [RFC 8174][rfc8174]) when, and only when, they appear in all capitals, as shown here.
- **Hex.** An integer is written `0x` followed by lowercase hex digits with no redundant leading zero (`0x0` is zero).
  Bytes are written `0x` followed by two lowercase hex digits per byte (`0x` is no bytes).
- **ckbhash** is BLAKE2b with a 32-byte digest and the personalization `ckb-default-hash`; **blake160** is the first 20
  bytes of ckbhash ([RFC 0022 L385-L388][rfc0022-hash]). `u64le(n)` is n as 8 little-endian bytes.
- **Molecule** is CKB's serialization ([RFC 0008][rfc0008]); the CKB types are those of ckb v0.210.0's schema
  ([`blockchain.mol` L1-L118][schema]). A transaction hash is ckbhash of the Molecule `RawTransaction`; a script hash
  is ckbhash of the Molecule `Script`; a header hash is ckbhash of the 208-byte Molecule `Header`
  ([RFC 0022 L392-L403][rfc0022-txhash]).
- **CKB RPC JSON** is the JSON form of the CKB types that the node's RPC uses ([RPC types][rpc-types]).

### 1.2 Terms

- **Reader:** any tool that reads a Sigsheet file: to show it, sign it, merge it or finalize it.
- **Lock group:** the inputs whose spent outputs have the same lock script, identified by that lock script's hash, in
  the order of their first input.
- **Kind:** what version 1 knows a lock group to be, from the spent cell's lock code hash and hash type (section 6):
  the single-key lock or one of the three multisig deployments. A group of any other lock is **carried**.
- **Member:** a key hash listed in a multisig config (N of them); the lock needs **M** signatures (the threshold), and
  the first **R** members must all be among them (`require_first_n`).
- **Signer:** the key hash a signature is filed under.
- **Template:** the first witness of a group of a kind version 1 signs, without its lock (section 4).

## 2. The file

A Sigsheet file is one JSON object with **exactly** these seven fields; a reader MUST refuse a file with any other
field ([D1][dr-3]; [design record 3.1][dr-31]):

| Field | Holds |
|---|---|
| `version` | `"0x1"` |
| `transaction` | The transaction in CKB RPC JSON, with its witness templates |
| `context` | `{transaction hash: raw previous transaction}`, one entry per transaction an input spends from |
| `headers` | `{block hash: header}`, one entry per header dep |
| `inclusion_proofs` | `{transaction hash: transaction proof}`, for the previous transactions of Nervos DAO withdrawing inputs; empty when unused |
| `multisig_configs` | `{blake160(multisig script): {public_key_hashes, require_first_n, threshold}}` |
| `signatures` | `{lock script hash: {signer key hash: 65-byte signature}}` |

### 2.1 `version`

The string `"0x1"`. A reader MUST refuse a version it doesn't know ([design record 3.1][dr-31]).

### 2.2 `transaction`

The transaction as the node's `send_transaction` takes it: exactly `version`, `cell_deps`, `header_deps`, `inputs`,
`outputs`, `outputs_data` and `witnesses`, and no `hash`. An absent type script is `"type": null`
([CellOutput][rpc-celloutput]). Witnesses are Molecule bytes in hex. The first witness of each group of a kind version
1 signs is a template (section 4); every other witness is kept exactly as it will be sent, because the lock's message
covers the group's other witnesses and every witness beyond the inputs (section 6.2). `outputs` and `outputs_data`
MUST have the same length, and an out point MUST NOT appear twice among the inputs ([D4][dr-3]; [XRT-2 L3][xrt2]: a
duplicate input was accepted before this rule, with a fee shown 1,000.001 CKB too high).

### 2.3 `context`

Each input's previous transaction, keyed by its hash: the raw transaction only, exactly `version`, `cell_deps`,
`header_deps`, `inputs`, `outputs` and `outputs_data`, without witnesses and without `hash`. Each entry MUST hash to its
key, every input's out point MUST find its entry with an output at its index, and an entry that no input spends MUST be
refused ([D4][dr-3]). The message doesn't cover the input cells, only their out points (section 13.1), so this is what
proves an input's capacity, lock, type and data to a signer ([X4][x4-attacks] attack 1: a falsified input cell is
refused; [XRT-2][xrt2] F03: an unused entry is refused).

### 2.4 `headers`

A header for every header dep, keyed by its block hash: the header in CKB RPC JSON without `hash`, exactly
`compact_target`, `dao`, `epoch`, `extra_hash`, `nonce`, `number`, `parent_hash`, `proposals_hash`, `timestamp`,
`transactions_root` and `version` ([Header][rpc-header]). Each MUST hash to its key; a header dep without its header,
and a header that isn't a header dep, MUST be refused ([D5][dr-3]).

### 2.5 `inclusion_proofs`

For the previous transaction of a Nervos DAO withdrawing input (section 9.2), the node's transaction proof
(`get_transaction_proof`, [TransactionProof][rpc-proof]): `block_hash`, `proof` (`indices`, `lemmas`) and
`witnesses_root`, keyed by the transaction's hash. A proof MUST be keyed by the previous transaction of such an input,
its block hash MUST be a carried header, and it MUST verify against that header: the CKB Merkle Tree root of the
transaction hash with the proof's lemmas ([RFC 0006 L13-L155][rfc0006]), merged with `witnesses_root` by ckbhash, MUST
equal the header's `transactions_root` ([RFC 0027 L249-L263][rfc0027]). A proof is OPTIONAL; without one, the fee is
shown as an upper bound ([D5][dr-3]; [XRTb-3][xrtb3]: on the devnet, both proofs of a two-deposit withdrawal verified;
the same proof with its block hash changed to the deposit block failed).

### 2.6 `multisig_configs`

Each multisig config keyed by blake160 of its multisig script, `S || R || M || N || the N key hashes` with S = 0
([multisig lock L13-L28][ms-layout]): `public_key_hashes` (20-byte hashes, in member order), `require_first_n` (R) and
`threshold` (M), with R and M as JSON integers ([D6][dr-3]). There is no code hash, hash type or since: the lock kind
and the since come from the input cell ([ckb-cli PR #652][ckb-cli-652]; [X3][x3] S11). A config MUST have 1 to 255 members,
1 <= M <= N and R <= M; it MUST NOT list a member twice, as ckb-sdk refuses such configs ([XRT-1][xrt1]); its key MUST
be blake160 of its script ([X4][x4-attacks] attack 7); and its key MUST occur in the lock args of some input, at any
offset, so that a config for a kind version 1 carries (an Omnilock multisig-mode group keeps its key at args bytes
1-20) is kept while a config for no input is refused ([XRTb-2][xrtb2] F10: 50 such configs took a file from 2,685 to
14,585 bytes with the same unsigned id). Every multisig group of a kind version 1 signs MUST have the config its args
name: the args' first 20 bytes.

### 2.7 `signatures`

Signatures keyed by lock group (the lock script hash) and then by signer (a 20-byte key hash): each a 65-byte
signature `r || s || recovery id`. Keying by group, not by lock args, keeps apart two groups that share a multisig
script under two deployments, whose messages differ ([D7][dr-3]; [X3][x3] S10). A group's map MUST NOT be empty. For a
single-key group the signer is the 20-byte args. Section 7 says how a reader verifies them.

## 3. The canonical form

A Sigsheet file MUST be the RFC 8785 ([JCS][rfc8785]) serialization of its value, in ASCII, with no trailing newline
([D2][dr-3]; [X2][x2]: 12 of 12 cases lossless and canonical). For the values a file holds (objects with ASCII keys,
arrays, ASCII strings, integers below 2^53 and `null`), RFC 8785 means: no whitespace between tokens; object members
sorted by key; strings with `"` and `\` escaped, and control characters written as RFC 8785 says (none occurs in a
valid file); integers as their decimal digits. Hex follows section 1.1: the node also accepts uppercase hex on input
([`uints.rs` L56-L95][ckb-uints]), but a file MUST use lowercase. An absent type script MUST be `"type": null`
(CCC leaves the field out; a file fixes one form, [X6][x6] section 3). R and M MUST be JSON integers. Every other
number is a hex string.

A reader MUST check the canonical form **first**, on the parsed file, before anything else and before any signature is
dropped: it parses the file, re-encodes the value by RFC 8785 and refuses the file on any byte difference
([XRT-2][xrt2] F10). A value outside the domain (a fraction or an exponent, NaN, a repeated key, a non-ASCII byte) MUST
be refused. One content has one byte string, so files can be compared, hashed and merged byte for byte.

## 4. Witness templates and the unsigned id

The first witness of each group of a kind version 1 signs is a **template**: the witness without its lock
([D3][dr-3]). A template MUST be `0x`, or a Molecule `WitnessArgs` with exactly its three fields that re-encodes to
itself, whose `lock` is absent and whose `input_type` or `output_type` is present; a `WitnessArgs` with all three
absent MUST be written `0x`, so that one template has one form and one unsigned id (the design's prototype,
[`core.py` L322-L325][core-template]). The locks and the DAO script read `WitnessArgs` in Molecule's non-compatible mode, which
refuses a fourth field ([`common.h` L68-L84][common-witness]; [`dao.c` L81][dao-81]); before this rule a template with
a fourth field was accepted ([XRT-2][xrt2] L2). Every other witness MUST be kept exactly; a template must keep
`input_type` and `output_type`, which the message covers ([X2][x2]: without witnesses, case S9 fails). The first input
of such a group MUST have a witness.

The **unsigned id** identifies the transaction a file is for:

    unsigned_id = ckbhash(transaction hash || for each witness, in order: u64le(length) || witness)

over the file's witnesses as they are, templates included. Files with different unsigned ids describe different
transactions and MUST NOT be merged (section 8.1; [design record 3.1][dr-31]; [X4][x4-attacks] attacks 2-3: a merge
with a swapped transaction is refused).

## 5. Reading a file: the checks

A reader MUST run the checks below in this order, and MUST refuse a file at the first that fails, naming its check id.
Checks 1-31 run offline, from the file alone; the four `node.*` checks run when a tool creates or sends the transaction
(section 10). Signatures are then verified (section 7): a signature that fails is
dropped and named with a reason id, never a reason to refuse the file. A reader therefore gives one of three outcomes:
refused (with the check id); accepted with named signatures dropped; accepted. The checks marked "needs a node" can't
be settled by any file; a tool runs them when it creates or sends the transaction (section 10), and none of them can
move value if it fails: the transaction fails on chain ([design record 5.2][dr-52], last paragraph).

| # | Check id | The file is refused unless | Runs |
|---|---|---|---|
| 1 | `canonical.json` | The file is ASCII text holding one JSON value in the domain: no fraction or exponent, no NaN or Infinity, no repeated key, integers below 2^53. | offline |
| 2 | `canonical.form` | Re-encoding the parsed value by RFC 8785 gives exactly the file's bytes. | offline |
| 3 | `schema.fields` | The file is an object with exactly the seven fields. | offline |
| 4 | `schema.version` | `version` is "0x1". | offline |
| 5 | `schema.transaction` | `transaction` is a transaction in CKB RPC JSON with exactly its seven fields and the hex rules. | offline |
| 6 | `schema.context` | `context` maps 32-byte hashes to raw transactions with exactly their six fields. | offline |
| 7 | `schema.headers` | `headers` maps 32-byte hashes to headers with exactly their eleven fields. | offline |
| 8 | `schema.inclusion-proofs` | `inclusion_proofs` maps 32-byte hashes to transaction proofs. | offline |
| 9 | `schema.multisig-configs` | `multisig_configs` maps 20-byte keys to configs whose R and M are integers from 0 to 255. | offline |
| 10 | `schema.signatures` | `signatures` maps 32-byte lock hashes to non-empty maps of 20-byte signers to 65-byte signatures. | offline |
| 11 | `transaction.outputs-data` | `outputs` and `outputs_data` have the same length. | offline |
| 12 | `transaction.duplicate-input` | No out point appears twice among the inputs. | offline |
| 13 | `context.hash` | Every context entry hashes to its key. | offline |
| 14 | `context.missing` | Every input's previous transaction is in the context, with an output at the input's index. | offline |
| 15 | `context.unused` | Every context entry is a previous transaction of some input. | offline |
| 16 | `headers.hash` | Every header hashes to its key. | offline |
| 17 | `headers.missing` | Every header dep has its header. | offline |
| 18 | `headers.unused` | Every header is a header dep. | offline |
| 19 | `lock.single-key-args` | A single-key lock's args are 20 bytes. | offline |
| 20 | `lock.multisig-args` | A multisig lock's args are 20 or 28 bytes. | offline |
| 21 | `multisig-configs.values` | Each config has 1 to 255 members, 1 <= M <= N and R <= M. | offline |
| 22 | `multisig-configs.repeated-key` | No config lists a member twice. | offline |
| 23 | `multisig-configs.hash` | Each config's key is blake160 of its multisig script. | offline |
| 24 | `multisig-configs.unused` | Each config's key occurs in the lock args of some input. | offline |
| 25 | `multisig-configs.missing` | Every multisig group has the config its args name. | offline |
| 26 | `template.missing` | The first input of every group of a kind version 1 signs has a witness. | offline |
| 27 | `template.form` | That witness is `0x`, or a three-field WitnessArgs that re-encodes to itself, with no lock, and with an `input_type` or an `output_type`. | offline |
| 28 | `inclusion-proofs.target` | Each proof's key is the previous transaction of a Nervos DAO withdrawing input. | offline |
| 29 | `inclusion-proofs.header` | Each proof's block hash is a carried header. | offline |
| 30 | `inclusion-proofs.verify` | Each proof verifies against that header's transactions root. | offline |
| 31 | `signatures.carried-limit` | A group of a kind the reader carries has at most 255 signatures. | offline |
| - | `node.unspent` | Every input is still unspent. | needs a node: Only the chain knows whether an out point has been spent. |
| - | `node.scripts` | The cell deps resolve and every type script passes. | needs a node: The scripts run against the live cells and their own code. |
| - | `node.network` | For a `data1` lock whose code cell the wallet doesn't know, the inputs are on the wallet's network. | needs a node: The file names no network, and a `data1` code hash is the same on every chain. |
| - | `node.genesis` | For a genesis multisig group with N > 10, the finalized set passes `test_tx_pool_accept` before sending. | needs a node: The genesis binary rejects some valid sets, and their pattern is measured only up to N = 24. |

## 6. The lock kinds and their messages

### 6.1 The kinds version 1 signs

A reader MUST take a lock's kind only from the spent cell's lock code hash and hash type, never from a field of the
file ([D8][dr-3]):

| Kind | Code hash | Hash type | Networks |
|---|---|---|---|
| single-key | `0x9bd7e06f3ecf4be0f2fcd2188b23f1b9fcc88e5d4b65a8637b17723bbda3cce8` | `type` | mainnet and testnet ([RFC 0024][rfc0024]) |
| multisig-genesis | `0x5c5069eb0857efc65e1bca0c07df34c31663b3622fd3876c876320fc9634e2a8` | `type` | mainnet and testnet ([RFC 0024][rfc0024]) |
| multisig-2024 | `0xd1a9f877aed3f5e07cb9c52b61ab96d06f250ae6883cc7f0a2423db0976fc821` | `type` | mainnet ([CCC L66-L82][ccc-mainnet]) |
| multisig-2024 | `0x765b3ed6ae264b335d07e73ac332bf2c0f38f8d3340ed521cb447b4c42dd5f09` | `type` | testnet ([CCC L66-L82][ccc-testnet]) |
| multisig-v2 | `0x36c971b8d41fbd94aabca77dc75e826729ac98447b46f91e00796155dddb0d29` | `data1` | mainnet and testnet ([CCC L83-L99][ccc-mainnet]) |

The genesis multisig binary is from the system scripts' v0.5 code, the 2024 deployment's from commit `9341664`, v2's
the current file ([design record][dr-3], D8). On a development chain the 2024 binary may sit under the chain's own type
id, with another code hash; a reader MAY accept such a chain's code hashes as configuration, never as a field of the
file (the vectors list theirs).

A single-key group's args MUST be 20 bytes, as the lock requires ([`sighash_all.c` L106][sighash-args];
[XRTb-2][xrtb2] F11: 32-byte args were accepted before this rule). A multisig group's args MUST be 20 bytes, or 28
bytes when they end with an 8-byte little-endian since; any other length fails on chain ([multisig lock L30-L34,
L110-L118][ms-args]).

Every other lock is **carried**: version 1 keeps its group's signatures unchanged and unverified (section 7) and
leaves its witness as in the template when it finalizes (section 8.3). In particular, version 1 carries Omnilock's
multisig mode without signing it: an Omnilock group's config is kept when its key occurs in the group's args
(`<identity, 21 bytes> <omni_lock args>`, [`omni_lock.c` L136-L140][omnilock]), but its signatures are neither
verified nor written ([XRTb-2][xrtb2] F07).

### 6.2 The message rule

The message is the lock's own rule, computed from the file alone ([D9][dr-3]; [X1][x1]: 15 lock groups agree byte for
byte across CCC, ckb-cli, ckb-sdk and an independent implementation). For a group, with the group's first witness W
built from its template by setting `lock` to the zeroed lock and keeping `input_type` and `output_type`:

    message = ckbhash(
        transaction hash
        || u64le(len(W)) || W
        || for each other input of the group, in order, while it has a witness: u64le(len(w)) || w
        || for each witness at an index >= the number of inputs: u64le(len(w)) || w
    )

This is the rule of the multisig lock ([L205-L281][ms-message]: the group loop stops at the first group input with no
witness, L228-L250; the witnesses beyond the inputs, L252-L278) and of the single-key lock ([L154-L215][sighash-message]).
The zeroed lock is:

- **single-key:** 65 zero bytes; the final lock is the one 65-byte signature ([L131][sighash-lock]);
- **multisig (all three deployments):** the multisig script `S || R || M || N || key hashes` followed by M × 65 zero
  bytes; the final lock is exactly `4 + 20N + 65M` bytes ([L163-L189][ms-size]).

## 7. Signatures

A reader verifies each signature of an accepted file, in this order for each entry, and drops a failing entry with its
reason ([D11][dr-3]):

| Reason id | The signature is dropped when |
|---|---|
| `drop.no-group` | The entry is filed under a lock hash that is no lock group of the transaction. |
| `drop.not-member` | The filed signer isn't a member of the group; checked before any key recovery. |
| `drop.invalid` | The 65 bytes aren't a signature a key can be recovered from. |
| `drop.mismatch` | The signature recovers, over the group's message, to a key other than the filed signer. |

Membership MUST be checked before any key recovery: then junk filed under non-members costs nothing to drop
([XRT-2][xrt2] F09: 20,000 junk entries read in 0.022 s instead of 106.49 s). Recovery follows the locks' library: r and
s are big-endian and MUST be non-zero and below the group order, the recovery id is byte 64 and MUST be 0 to 3, and
the key is compared by blake160 of its 33-byte compressed form ([secp256k1 recovery L38-L121][secp-recover];
[multisig lock L300-L330][ms-recover]). A kept signature MUST be normalized to low-s (s <= N/2, flipping the recovery
id's parity bit): the locks accept a signature's high-s twin, so a member can have two valid byte strings for one
message, and normalizing makes every reader keep the same one ([X4][x4-highs]: the twin was committed on all three
deployments). Signatures beyond M MUST be kept until finalizing.

A group of a carried kind keeps its entries unchanged and unverified, at most 255 of them (`signatures.carried-limit`);
an entry under a lock hash that is no group of the transaction is dropped.

## 8. Merge, ready and finalize

### 8.1 Merge

Anyone MAY merge copies of a file, in any order and any grouping ([D11][dr-3]):

- Only files the reader accepts are merged; a refused file refuses the merge with that file's check id.
- Every file MUST have the same unsigned id.
- The result keeps every verified member signature in low-s form, the smaller bytes when one signer has two, and
  signatures beyond M; it keeps only the context entries some input spends; it unites the configs (each is keyed by
  blake160 of its multisig script, so one key has one content) and the inclusion proofs; when two files carry different
  verified proofs for one transaction, it keeps the proof whose canonical encoding (section 3) is the smaller bytes;
  dropped entries don't reach it.
- Entries of a carried kind are kept unchanged; two different entries under one signer in such a group MUST refuse the
  merge, because no reader of this version can tell which is valid. A reader that signs the kind resolves them by
  verifying ([XRTb-2][xrtb2] F01: under a "smaller bytes" rule, 65 zero bytes replaced a valid signature).

| Check id | The merge is refused unless |
|---|---|
| `merge.unsigned-id` | Every file has the same unsigned id. |
| `merge.carried-conflict` | No signer has two different entries in a group of a kind the reader carries. |

The result is one byte string in any order and grouping ([X3][x3]: 3,150 of 3,150 trials; [X3a][x3a]: 2,000 of 2,000,
where BIP-174's and PCZT's rules failed). The vectors merge each case's copies in 200 random orders and groupings.

### 8.2 Ready

A multisig group is ready when its usable verified signers include the first R members and number at least M. A
single-key group is ready when its one signer, the args' key, has a verified signature. A file is ready when every
group of a kind version 1 signs is ready.

**The genesis rule.** The genesis multisig binary rejects some valid signature sets: written in member order, a set
fails exactly when the member at position 10 (the 11th) signs and M <= 10, or the member at position 18 signs and
M = 1, for N up to 24; the 2024 and v2 binaries accept every set ([design record 5.5][dr-55]; [XRT-1][xrt1];
[XRTb-1][xrtb1]). So, in a genesis group, position 10 is not usable when M <= 10 and position 18 not when M = 1. Since
R <= M, neither is ever a required member. A genesis group whose only usable sets need a skipped member is not ready
until another member signs.

### 8.3 Finalize

Anyone MAY finalize a ready file ([D12][dr-3]). For each multisig group, finalize takes the first R members, then the
lowest usable member positions until it has M, and writes their signatures in member order after the multisig script:
a lock of exactly `4 + 20N + 65M` bytes, put in the group's first witness with the template's `input_type` and
`output_type`. A single-key group's lock is its 65-byte signature. Every other witness is kept as it is.

**Partial finalize.** When carried groups are present, finalize writes the groups version 1 signs and leaves every
carried group's witness as in the template; that group's own signer completes it ([XRT-3][xrt3]: a lock the reader
didn't sign was finalized partially, then signed by its own signer, and committed).

For a genesis group with N > 10, the finalizer MUST check its transaction with a node before sending
(`node.genesis`, section 10.2; [design record 5.5][dr-55]).

## 9. What a signer is shown

### 9.1 Derived data only

A reader MUST show a signer only what it derives from the checked file, never a label or a description the file
declares: the schema has no field for one ([D10][dr-3]; [X4][x4-attacks] attack 9: a display field is refused; the
incidents behind this rule are in [design record 5.6][dr-56]). It MUST show:

- every output, with its capacity, lock, type script, and the hash and size of its data; an output with no type script
  and no data whose lock is some input's lock is labelled as going back to the lock of that input, and any other output
  is a payment. A type script runs again when its cell is spent ([RFC 0022 L217][rfc0022-type]), so "back to an input's
  lock" requires no type and no data;
- every input, with the same fields, from its previous transaction;
- the fee (section 9.2);
- each lock group, its kind, its members, who has signed and whether it is ready;
- the network, `mainnet` or `testnet`, when the transaction's cell deps include known cell deps of that network only
  ([CCC's tables][ccc-mainnet]); otherwise `unknown`, and then each lock as its script with both address forms, labelled
  ([RFC 0021][rfc0021]: full-format addresses, `ckb` and `ckt`). The file has no network field: a declared network is
  a claim no reader can check ([X4][x4-attacks] attack 6c);
- the amounts of known tokens in and out: sUDT and xUDT, each a little-endian u128 at the start of the cell data
  ([RFC 0025 L105-L128][rfc0025]; [RFC 0052 L328-L370][rfc0052]), per cell and in total per token type script;
- warnings: an input's type script that appears on no output (its cell is consumed, and with it any token amount it
  holds; [XRTb-2][xrtb2] F09: a 1,000,000-unit xUDT cell consumed was shown only as "fee: 0.001 CKB" before this rule);
  a since the lock will reject (below); a genesis group with N > 10, which is checked with a node when sent.

**The since warning** follows each deployment's own rule ([`common.h` L91-L125][common-since]): the genesis and 2024
deployments always check the since, against 0 when the args are 20 bytes, and v2 checks it only when the args are 28
bytes (genesis: [v0.5.1 L82-L84, L158][ms-since-genesis]; 2024: [`9341664` L117-L119, L199][ms-since-2024]; v2: [L116-L123][ms-since-v2]); then every group input MUST have the same since flags
byte as the required since and a value at least the required one, compared as an epoch with a fraction when the flags
byte is `0x20` ([`utils.h` L14-L57][utils-epoch]). A reader MUST warn when a group input fails this ([XRT-3][xrt3] part
C: since `0x8000000000000001` under genesis with 20-byte args was rejected by the lock).

### 9.2 The fee and Nervos DAO withdrawals

The fee is the inputs' capacity minus the outputs'. In a Nervos DAO withdrawal the outputs may exceed the inputs
([RFC 0023 L44][rfc0023-44]), so a reader MUST count each withdrawing input at its maximum withdraw ([D5][dr-3]). A
reader MUST follow the DAO script ([`dao.c`][dao]) where it differs from RFC 0023's text:

- An input is a withdrawing cell when its type script is the DAO's (`0x82d76d1b75fe2fd9a27dfbaa65a039221a380d76c926f378d3f81cf3e7e13f2e`,
  `type`, empty args) and its 8 bytes of data hold a positive number, the deposit block number; 8 zero bytes are a
  deposited cell, counted at its capacity ([`dao.c` L425-L450][dao-cells], L557).
- The deposit header is `header_deps[i]`, where i is the **first byte** of the input's witness `input_type`, which must
  be exactly 8 bytes. RFC 0023 describes the index as a 64-bit integer ([RFC 0023 L76][rfc0023-76]); the script reads
  only its first byte ([`dao.c` L63-L98][dao-index]), and this specification follows the script. The deposit header's
  number must equal the cell's deposit block number ([L192][dao-192]).
- The withdrawing header is the block that holds the withdrawing cell, which the script loads by the input itself
  ([L197][dao-197]). A reader MUST take it only from a verified inclusion proof of the input's previous transaction.
- The amount is `occupied + (capacity − occupied) × AR_withdraw / AR_deposit` in integer division, with AR the
  little-endian u64 at bytes 8-16 of a header's `dao` field and the occupied capacity that of the cell
  ([L284-L316][dao-amount]; [RFC 0023 L128-L134][rfc0023-128]).

With a verified proof for every withdrawing input the fee is **exact**. Without one, the input counts at the largest
amount any carried header other than its deposit header allows, and the fee is shown as **"at most"** that bound: the
withdrawing header is a header dep of the transaction, and the accumulated rate never falls, so the bound is never
below the real fee. A reader MUST NOT lower the fee with a block that isn't proven. When the DAO script would reject an
input (no deposit header it can read, a deposit number that doesn't match, a withdrawing header that isn't later than
the deposit header), the reader shows no fee and warns. With the proofs, the minimal since is also computed offline:
the deposit epoch plus the deposited epochs rounded up to whole 180-epoch periods ([L203-L259][dao-since]).

[XRTb-3][xrtb3], two deposits withdrawn together on the devnet: the node's fee 0.001 CKB; inputs minus outputs −7.125
CKB; with proofs exactly 0.001 CKB, and each input's amount the node's maximum withdraw; without proofs "at most"
4.63600414 CKB; with the output cut to the deposits, the node's 7.12722788 CKB, where inputs minus outputs shows 0.001.

## 10. Creating and sending: the steps that need a node

### 10.1 Creating

Creating a file is the one step besides sending that needs a node ([D14][dr-3]; [XRT-4][xrt4]: ckb-cli and CCC
created byte-identical files for one transaction, and both flows committed). From a built transaction with its
witness templates, the creator:

- fetches each input's previous transaction (`get_transaction`) and keeps its raw part, checking its hash;
- fetches a header for every header dep (`get_header`), checking its hash;
- for each Nervos DAO withdrawing input, fetches the proof of its previous transaction (`get_transaction_proof`);
- takes each multisig config from the user's own records or the tool's settings;
- writes the canonical file with empty `signatures`, and MAY sign it before passing it on ([D14][dr-3]; the methods
  and their results: [the RPC types][rpc-types]).

### 10.2 Sending

Sending submits the final transaction to a node, which checks what no file can: that the inputs are still unspent
(`node.unspent`), that the cell deps resolve and every type script passes (`node.scripts`), and the since. For a
`data1` lock whose code comes from a cell the wallet doesn't know, only the node tells which network the inputs are on
(`node.network`). For a genesis multisig group with N > 10, the sender MUST run `test_tx_pool_accept` before
`send_transaction` (`node.genesis`): the genesis binary's rejected sets are measured only up to N = 24
([design record 5.5][dr-55]). Replay is stopped by the chain itself: an out point can't be spent twice, and a signature
covers the transaction hash, which covers every input's out point ([X4][x4-attacks] attacks 6a and 6b; the networks'
genesis transactions differ, so no out point exists on both).

## 11. Gathering, signing and hardware wallets

### 11.1 Gathering

The file itself moves ([D13][dr-3]): from signer to signer, or each signer posts a copy (in a pull request, a chat, an
email) and anyone merges the copies (section 8.1). There is no collector role. A relay is optional and outside version
1 ([X5][x5]: seven devnet flows with ckb-cli, CCC and Neuron, all committed).

### 11.2 Each wallet signs with its own signer

Each tool signs with its own signer and key storage, and adds the signature under its group and signer ([D15][dr-3];
[X6][x6] section 1). A tool that doesn't sign a kind passes the file on unchanged.

### 11.3 Hardware wallets

A device doesn't parse the file: the host sends the device the bytes it needs, as Neuron's Ledger path does today, and
the file carries everything that path sends ([D19][dr-3]; [design record 5.7][dr-57]; [XQ14][xq14]).

## 12. Versions and extension

A new lock kind needs no new field and no version change ([D18][dr-3]): its definition states its code hashes and hash
types, where its config key sits in its args, how its witness carries the multisig bytes, and its message rule; until
a reader knows it, the reader carries it (section 6.1). A new top-level field changes `version`, and a reader MUST
refuse a version it doesn't know (section 2.1) and a field it doesn't know (`schema.fields`).

## 13. Security considerations

### 13.1 The root

The multisig message covers the transaction hash and the witnesses, **not the input cells**: a signer that trusts an
input amount it can't check can be robbed through the fee, as Bitcoin's hardware wallets were before they required
full previous transactions (CVE-2020-14199) ([design record 5.1][dr-51]). Sigsheet carries every previous transaction
and checks it by hash, and every check below runs offline, from the file alone.

### 13.2 Attacks and what stops them

| Attack | What stops it | Check | Measured |
|---|---|---|---|
| Falsified input cells (the fee attack) | Each previous transaction must hash to its input's out point | `context.hash` | [X4][x4-attacks] attack 1: refused |
| A Nervos DAO withdrawal hiding its fee | Headers carried and checked; each DAO input at its maximum withdraw, the withdrawing block only from a verified proof, otherwise an upper bound | `headers.*`, `inclusion-proofs.*` | [XRTb-3][xrtb3] |
| A swapped transaction, altered outputs or fees | Signatures are checked against the file's own message; files for different transactions don't merge | `drop.mismatch`, `merge.unsigned-id` | [X4][x4-attacks] attacks 2-3 |
| Signatures from non-members | The filed signer must be a member, checked before recovery | `drop.not-member` | [X4][x4-attacks] attack 4; [XRT-2][xrt2] F09 |
| Junk that blocks finalizing | Verify, members only, low-s, key by signer, the smaller bytes on a conflict | section 7 | [X4][x4-attacks] attack 5; [X3][x3] |
| A swapped multisig config | The config must hash to its key | `multisig-configs.hash` | [X4][x4-attacks] attack 7 |
| A changed covered witness | The message covers it | `drop.mismatch` | [X4][x4-attacks] attack 10 |
| Display fields | The schema has none | `schema.fields` | [X4][x4-attacks] attack 9 |
| Junk under a member in a group the reader carries | Two different entries under one signer refuse the merge | `merge.carried-conflict` | [XRTb-2][xrtb2] F01 |
| Configs for no input, to bloat every copy | A config must occur in some input's lock args | `multisig-configs.unused` | [XRTb-2][xrtb2] F10 |
| Tokens consumed by a transaction that shows only CKB | Each input's data, the token amounts in and out, a warning when a type script leaves | section 9.1 | [XRTb-2][xrtb2] F09 |
| One out point listed twice | Refused | `transaction.duplicate-input` | [XRT-2][xrt2] L3 |
| A template with a fourth field | Refused | `template.form` | [XRT-2][xrt2] L2 |
| A since the lock will reject | The since warning follows each deployment's rule | section 9.1 | [XRT-3][xrt3] part C |
| A type script hiding in "change" | "Back to an input's lock" only with no type and no data | section 9.1 | rule |
| A code deployment with a swapped binary | Each output's data hash is shown | section 9.1 | rule |
| Replay, on one network or across networks | Out points can't be spent twice; the networks share no out point | section 10.2 | [X4][x4-attacks] attacks 6a-6b |

### 13.3 Two valid signatures from one member

The locks accept a signature's high-s twin, so one member can have two valid signatures for one message
([design record 5.4][dr-54]). Merging normalizes to low-s and keeps the smaller bytes, so every order of merging gives
one result.

### 13.4 What a signer still decides

A signer is shown only derived data, but still has to read the outputs: Sigsheet shows the true destination, amount,
fee and code hash, and can't decide whether they are intended ([design record 5.6][dr-56]).

### 13.5 Files and sizes

A file carries every previous transaction in full, so a transaction spending from a large one makes a large file
(PR #34's previous transaction is 284,008 bytes; hex JSON doubles it, [X2a][x2a]). The node's limits still apply: a
transaction in the pool is at most 512,000 bytes ([`tx_pool.rs` L309][ckb-txpool]).

## Annex A (informative). The CoBuild profile

A Sigsheet maps losslessly onto a profile of CoBuild's `BuildingPacketV1`, so a CoBuild tool can carry a Sigsheet and
the reverse ([D16][dr-3]; [design record 6.1][dr-61]; [X2][x2] section 3: 12 of 12 cases round-trip byte for byte;
[X6][x6] section 4: a second implementation agrees). The packet's schema is
[`schemas/basic.mol` L7-L50][cobuild-schema] (`BuildingPacketV1 {message, payload, resolved_inputs, change_output,
script_infos, lock_actions}`), and the multisig action is [`multisig-lock-action.js` L15-L45][cobuild-multisig]
(`MultisigAction {config, signed}`), to which the profile adds `input_transactions`. The profile's rules
([`prototypes/fmt_a.py`][fmt-a]):

- `message` has no actions, and `change_output` is none;
- `payload` is the transaction with its templates; a single-key group's signature sits in its first witness;
- `resolved_inputs` lists every input's spent output, which must equal the carried previous transaction's, with empty
  data;
- `script_infos` holds one `ScriptInfo` per multisig deployment the transaction spends from;
- `lock_actions` holds one `Action` per multisig group, in order of the group's first input, whose data is the
  `MultisigAction`: the config, the signatures sorted by key hash, and, in the first action only, every previous
  transaction without witnesses, sorted by hash.

**A Sigsheet carried as a building packet is safe only in tools that know the profile.** A CoBuild tool that doesn't
know it trusts `resolved_inputs`, which nothing proves: such a reader would show a fee of 1,000,000.00001186 CKB for a
real 0.00001186 ([X4][x4-attacks] attack 1b). The profile was measured on the design's first five fields; carrying
`headers`, `inclusion_proofs` and the entries of carried kinds in a packet is not yet defined, and a file that uses them
has no packet form in this draft.

## Annex B (informative). The boundary with CKB IDL

Sigsheet complements CKB IDL instead of duplicating it ([D17][dr-3]; [design record 6.2][dr-62]). CKB IDL describes
what a script's witness must contain; Sigsheet carries one partly signed transaction between tools. Every Sigsheet
field is that transaction's data; none describes a signing rule, and a signer's message computation reads only the
transaction, the previous transactions and the multisig config ([X2][x2] section 4). The file carries no signing-rule
field: this specification names each lock by its code hash and hash type and states its message rule, and a later lock
kind takes its signing description from CKB IDL if CKB IDL defines one by then ([XC4][xc4]).

## Annex C (informative). The check ids

Every id a reader reports, and where this text states it. The test vectors name these ids.

| Id | Kind | Section |
|---|---|---|
| `canonical.json` | reader check, offline | 3 |
| `canonical.form` | reader check, offline | 3 |
| `schema.fields` | reader check, offline | 2 |
| `schema.version` | reader check, offline | 2 |
| `schema.transaction` | reader check, offline | 2 |
| `schema.context` | reader check, offline | 2 |
| `schema.headers` | reader check, offline | 2 |
| `schema.inclusion-proofs` | reader check, offline | 2 |
| `schema.multisig-configs` | reader check, offline | 2 |
| `schema.signatures` | reader check, offline | 2 |
| `transaction.outputs-data` | reader check, offline | 2.2 |
| `transaction.duplicate-input` | reader check, offline | 2.2 |
| `context.hash` | reader check, offline | 2.3 |
| `context.missing` | reader check, offline | 2.3 |
| `context.unused` | reader check, offline | 2.3 |
| `headers.hash` | reader check, offline | 2.4 |
| `headers.missing` | reader check, offline | 2.4 |
| `headers.unused` | reader check, offline | 2.4 |
| `lock.single-key-args` | reader check, offline | 6.1 |
| `lock.multisig-args` | reader check, offline | 6.1 |
| `multisig-configs.values` | reader check, offline | 2.6 |
| `multisig-configs.repeated-key` | reader check, offline | 2.6 |
| `multisig-configs.hash` | reader check, offline | 2.6 |
| `multisig-configs.unused` | reader check, offline | 2.6 |
| `multisig-configs.missing` | reader check, offline | 2.6 |
| `template.missing` | reader check, offline | 4 |
| `template.form` | reader check, offline | 4 |
| `inclusion-proofs.target` | reader check, offline | 2.5 |
| `inclusion-proofs.header` | reader check, offline | 2.5 |
| `inclusion-proofs.verify` | reader check, offline | 2.5 |
| `signatures.carried-limit` | reader check, offline | 7 |
| `drop.no-group` | drop reason | 7 |
| `drop.not-member` | drop reason | 7 |
| `drop.invalid` | drop reason | 7 |
| `drop.mismatch` | drop reason | 7 |
| `merge.unsigned-id` | merge refusal | 8.1 |
| `merge.carried-conflict` | merge refusal | 8.1 |
| `node.unspent` | needs a node | 10 |
| `node.scripts` | needs a node | 10 |
| `node.network` | needs a node | 10 |
| `node.genesis` | needs a node | 10 |

## Annex D (informative). The design decisions and where this text states each

| Decision ([design record 3][dr-3]) | Section |
|---|---|
| D1 One canonical JSON file, seven top-level fields | 2 |
| D2 RFC 8785, hex strings, Molecule hex witnesses, `"type": null`; the canonical check first | 3 |
| D3 Witness templates | 4 |
| D4 Previous transactions, raw part only, keyed by hash | 2.2, 2.3 |
| D5 Headers, inclusion proofs, the DAO-aware fee | 2.4, 2.5, 9.2 |
| D6 Multisig configs keyed by blake160(script) | 2.6 |
| D7 Signatures keyed by lock group and signer | 2.7, 7 |
| D8 The lock kind from the input cell's code hash and hash type | 6.1 |
| D9 The message is the lock's own rule | 6.2 |
| D10 Show only derived data | 9 |
| D11 Merge | 7, 8.1 |
| D12 Ready and finalize, the genesis rule, partial finalize | 8.2, 8.3 |
| D13 Gathering | 11.1 |
| D14 Creation inside each wallet | 10.1 |
| D15 Each wallet signs with its own signer | 11.2 |
| D16 CoBuild: a lossless profile of `BuildingPacketV1` | Annex A |
| D17 CKB IDL: no signing-rule field | Annex B |
| D18 Versions and extension | 12 |
| D19 Hardware wallets | 11.3 |

## Annex E. References

- [The design record][dr], `research` branch at `9b22e10f02f70a6dfa71d39791f74c74b1fd5902`.
- [RFC 2119][rfc2119], [RFC 8174][rfc8174]: requirement levels. [RFC 8785][rfc8785]: JSON Canonicalization Scheme.
- CKB RFCs at `0c945451c24194f4d34d81195c0159df0a67581a`: [0006][rfc0006], [0008][rfc0008], [0021][rfc0021],
  [0022][rfc0022], [0023][rfc0023], [0024][rfc0024], [0025][rfc0025], [0027][rfc0027], [0052][rfc0052].
- ckb-system-scripts at `72eb92fca090700dcb398cd8cad8fbd8bad40355`: [the multisig lock][ms], [the single-key lock][sighash],
  [`common.h`][common], [`utils.h`][utils-epoch], [`dao.c`][dao]; their secp256k1 library at
  `3ffde18a060aaf4df5b81e7d88355f1e99874650` ([recovery][secp-recover]).
- ckb v0.210.0 (`2592ddf0502cd4adfe886db893cccc866db3c60f`): [the schema][schema], [the RPC types][rpc-types].
- CCC at `7095ccad564b94ea2e59284cb4a364aa3499252e`: [mainnet][ccc-mainnet] and [testnet][ccc-testnet] scripts.
- Omnilock at `280dd97ac0930ea1ed766a18d49478229347c832`: [`omni_lock.c` L136-L140][omnilock].
- CoBuild: [`basic.mol`][cobuild-schema] at `e29514f9b1206b40f2bbc7b97e86c6f35373b0b0`,
  [`multisig-lock-action.js`][cobuild-multisig] at `84bdc99ad5e62f8e7a90a30e4d8bcdc1a53b468a`.

[dr]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/design-record.md
[dr-3]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/design-record.md#3-the-design-decisions-with-their-evidence
[dr-31]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/design-record.md#31-the-file-field-by-field
[dr-51]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/design-record.md#51-the-root-and-the-checks-that-answer-it
[dr-52]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/design-record.md#52-attacks-considered-and-how-the-design-answers-them
[dr-54]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/design-record.md#54-merging-when-a-member-has-two-valid-signatures
[dr-55]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/design-record.md#55-the-genesis-binary-rejects-some-valid-signature-sets
[dr-56]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/design-record.md#56-what-a-signer-sees
[dr-57]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/design-record.md#57-hardware-wallets
[dr-61]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/design-record.md#61-cobuild-builds-on-cobuild-where-cobuild-fits-c4
[dr-62]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/design-record.md#62-ckb-idl-complements-ckb-idl-instead-of-duplicating-it-c4
[x1]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/X1/results.md
[x2]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/X2/results.md
[x2a]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/X2a/results.md
[x3]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/X3/results.md
[x3a]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/X3a/results.md
[x4-attacks]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/X4/results.md#2-each-attack-in-each-format
[x4-highs]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/X4/results.md#1-the-lock-accepts-a-malleated-signature-on-all-three-deployments-run-on-chain
[x5]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/X5/results.md
[x6]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/X6/results.md
[xc4]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/XC4/results.md
[xq14]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/XQ14/results.md
[xrt1]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/XRT/results.md#xrt-1-which-valid-signature-sets-each-deployed-binary-accepts
[xrt2]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/XRT/results.md#xrt-2-prototype-checks-no-chain
[xrt3]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/XRT/results.md#xrt-3-a-lock-the-reader-doesnt-sign
[xrt4]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/XRT/results.md#xrt-4-creating-the-file-inside-the-wallets
[xrtb1]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/XRTb/results.md#xrtb-1-the-genesis-binary-with-a-required-member-and-a-set-no-order-fixes
[xrtb2]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/XRTb/results.md#xrtb-2-the-simpler-rules-against-the-design-rules-offline
[xrtb3]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/XRTb/results.md#xrtb-3-a-nervos-dao-withdrawal-of-two-deposits
[fmt-a]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/prototypes/fmt_a.py
[rfc2119]: https://www.rfc-editor.org/rfc/rfc2119
[rfc8174]: https://www.rfc-editor.org/rfc/rfc8174
[rfc8785]: https://www.rfc-editor.org/rfc/rfc8785
[rfc0006]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0006-merkle-tree/0006-merkle-tree.md#L13-L155
[rfc0008]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0008-serialization/0008-serialization.md
[rfc0021]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0021-ckb-address-format/0021-ckb-address-format.md#L25-L36
[rfc0022]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0022-transaction-structure/0022-transaction-structure.md
[rfc0022-hash]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0022-transaction-structure/0022-transaction-structure.md#L385-L388
[rfc0022-txhash]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0022-transaction-structure/0022-transaction-structure.md#L392-L403
[rfc0022-type]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0022-transaction-structure/0022-transaction-structure.md#L217
[rfc0023]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0023-dao-deposit-withdraw/0023-dao-deposit-withdraw.md
[rfc0023-44]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0023-dao-deposit-withdraw/0023-dao-deposit-withdraw.md#L44
[rfc0023-76]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0023-dao-deposit-withdraw/0023-dao-deposit-withdraw.md#L76
[rfc0023-128]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0023-dao-deposit-withdraw/0023-dao-deposit-withdraw.md#L128-L134
[rfc0024]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0024-ckb-genesis-script-list/0024-ckb-genesis-script-list.md
[rfc0025]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0025-simple-udt/0025-simple-udt.md#L105-L128
[rfc0027]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0027-block-structure/0027-block-structure.md#L249-L263
[rfc0052]: https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0052-extensible-udt/0052-extensible-udt.md#L328-L370
[ms]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c
[ms-layout]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c#L13-L28
[ms-args]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c#L110-L118
[ms-size]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c#L163-L189
[ms-message]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c#L205-L281
[ms-recover]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c#L300-L330
[sighash]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_sighash_all.c
[sighash-args]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_sighash_all.c#L106-L108
[sighash-lock]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_sighash_all.c#L131
[sighash-message]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_sighash_all.c#L154-L215
[common]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/common.h
[common-witness]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/common.h#L68-L84
[common-since]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/common.h#L91-L125
[utils-epoch]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/utils.h#L14-L57
[dao]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c
[dao-81]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c#L81
[dao-index]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c#L63-L98
[dao-192]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c#L192
[dao-197]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c#L197
[dao-since]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c#L203-L259
[dao-amount]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c#L284-L316
[dao-cells]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c#L425-L450
[secp-recover]: https://github.com/nervosnetwork/secp256k1/blob/3ffde18a060aaf4df5b81e7d88355f1e99874650/src/modules/recovery/main_impl.h#L38-L121
[schema]: https://github.com/nervosnetwork/ckb/blob/2592ddf0502cd4adfe886db893cccc866db3c60f/util/gen-types/schemas/blockchain.mol#L1-L118
[rpc-types]: https://github.com/nervosnetwork/ckb/blob/2592ddf0502cd4adfe886db893cccc866db3c60f/rpc/README.md
[rpc-celloutput]: https://github.com/nervosnetwork/ckb/blob/2592ddf0502cd4adfe886db893cccc866db3c60f/rpc/README.md#L5876-L5895
[rpc-header]: https://github.com/nervosnetwork/ckb/blob/2592ddf0502cd4adfe886db893cccc866db3c60f/rpc/README.md#L6356-L6419
[rpc-proof]: https://github.com/nervosnetwork/ckb/blob/2592ddf0502cd4adfe886db893cccc866db3c60f/rpc/README.md#L7589
[ckb-uints]: https://github.com/nervosnetwork/ckb/blob/2592ddf0502cd4adfe886db893cccc866db3c60f/util/jsonrpc-types/src/uints.rs#L56-L95
[ckb-txpool]: https://github.com/nervosnetwork/ckb/blob/2592ddf0502cd4adfe886db893cccc866db3c60f/util/types/src/core/tx_pool.rs#L309
[ccc-mainnet]: https://github.com/ckb-devrel/ccc/blob/7095ccad564b94ea2e59284cb4a364aa3499252e/packages/core/src/client/clientPublicMainnet.advanced.ts
[ccc-testnet]: https://github.com/ckb-devrel/ccc/blob/7095ccad564b94ea2e59284cb4a364aa3499252e/packages/core/src/client/clientPublicTestnet.advanced.ts
[omnilock]: https://github.com/nervosnetwork/omnilock/blob/280dd97ac0930ea1ed766a18d49478229347c832/c/omni_lock.c#L136-L140
[cobuild-schema]: https://github.com/cryptape/ckb-transaction-cobuild-poc/blob/e29514f9b1206b40f2bbc7b97e86c6f35373b0b0/schemas/basic.mol#L7-L50
[cobuild-multisig]: https://github.com/cryptape/ckb-multisig-cobuild-poc/blob/84bdc99ad5e62f8e7a90a30e4d8bcdc1a53b468a/src/lib/multisig-lock-action.js#L15-L45
[ms-since-genesis]: https://github.com/nervosnetwork/ckb-system-scripts/blob/fd2616660098a46fdb963ccb9f4c509cc8d2ec70/c/secp256k1_blake160_multisig_all.c#L82-L158
[ms-since-2024]: https://github.com/nervosnetwork/ckb-system-scripts/blob/934166406fafb33e299f5688a904cadb99b7d518/c/secp256k1_blake160_multisig_all.c#L117-L199
[ms-since-v2]: https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_multisig_all.c#L116-L123
[ckb-cli-652]: https://github.com/nervosnetwork/ckb-cli/pull/652
[core-template]: https://github.com/ILE-Labs/Sigsheet/blob/9b22e10f02f70a6dfa71d39791f74c74b1fd5902/experiments/prototypes/core.py#L322-L325
