# The paths considered, and why each was dropped

Seven design paths were considered for the format and for how signatures are gathered. Each was checked against the gates (G1, G2, C1-C5, [design record §1.2](design-record.md#12-the-goal)) and the ones that passed were scored ([scoreboard.md](scoreboard.md)). Scores are out of 100 for formats and out of 75 for ways of gathering; "measured" and "provisional" are as in the scoreboard. Every number is design-stage: measured on throwaway prototypes and patched copies of the wallets.

| Path | Idea | Outcome |
|---|---|---|
| **C** | Extend the JSON that ckb-cli and Neuron already write | **Chosen** (84 of 100) |
| **D** | Partial signatures inside the witness, plus a metadata envelope | **Merged into C** |
| **B** | A PSBT-style format, per input | Not chosen (74, scored with the witness templates added: "B+w") |
| **A** | A profile of CoBuild's building packet as the exchange format | Not chosen as the exchange format (64); **kept as the profile C maps onto** |
| **E** | Gathering over a relay or a P2P network | Not chosen for the first version (41 of 75, provisional); **an optional transport for a later version** |
| **F** | On-chain gathering in signature cells | Not chosen (24 of 75, provisional) |
| **G** | Threshold signatures (one combined signature) | **Dropped:** fails C1 and C3 |

## C: extend the JSON that ckb-cli and Neuron already write (chosen)

**The idea.** One canonical JSON file per transaction: the transaction with witness templates, the previous transactions that prove its inputs, the multisig configs, and every signature so far, keyed by lock group and signer. Signers pass the file along, or post copies that anyone merges; whoever holds a ready file finalizes it. The decisions are in [the design record, section 3](design-record.md#3-the-design-decisions-with-their-evidence).

**What the evidence showed:**
- 12 of 12 cases round-trip losslessly and canonically; every message recomputed from the file alone; 32 of 32 signatures verified ([X2](experiments/X2/results.md#1-round-trips)).
- It maps onto the building-packet profile (path A) and back, byte for byte, on 12 of 12 cases ([X2 §3](experiments/X2/results.md#3-c4-c-maps-losslessly-onto-the-building-packet-profile)), so it builds on CoBuild (C4).
- Merging gives the same bytes in any order: 3,150 of 3,150 trials ([X3](experiments/X3/results.md)); every attack is caught ([X4](experiments/X4/results.md)).
- ckb-cli, CCC and Neuron, each patched, signed one shared file in seven devnet flows, all committed ([X5](experiments/X5/results.md)); the patches were 381, 229 and 137 code lines, with each wallet's tests unchanged ([X6](experiments/X6/results.md)).

**What changed along the way, on the evidence:**
- **Keyed by lock group, not lock args:** two groups can share args (one multisig script under two deployments), and a map keyed by args mixes their signatures ([X3 §2](experiments/X3/results.md#2-signatures-must-be-keyed-by-lock-group-not-by-lock-args-s10)).
- **No code hash, hash type or since in a config:** the deployment is read from the input cell, as ckb-cli itself does since [PR #652](https://github.com/nervosnetwork/ckb-cli/pull/652); a declared field can name the wrong deployment, as in the real PR #34 file ([X1](experiments/X1/results.md#interoperability-findings)).
- **No description or status field:** unverified display fields are a spoofing surface ([X4](experiments/X4/results.md#2-each-attack-in-each-format), attack 9).
- **A formal canonical form** (RFC 8785), so that files can be compared and hashed.
- **Headers and inclusion proofs** for Nervos DAO withdrawals, **partial finalize**, **carrying other lock kinds' data**, **creation inside the wallets**, and **token display**, after the attacks in [the design record, section 5](design-record.md#5-security-analysis).

## D: partial signatures inside the witness (merged into C)

**The idea.** Keep partial signatures in the witness itself, in M zero-filled slots at the lock's final length (as CCC does), with a metadata envelope carrying the previous transactions.

**Why it was merged into C.** C and D were one JSON design with two places for partial signatures, and the in-witness place fails on the evidence:
- **An M-slot witness can't keep signatures beyond M.** PR #34 gathered five signatures for a threshold of three ([X1](experiments/X1/results.md#real-signatures)).
- **CCC's in-witness merge isn't order-independent.** The same five PR #34 files gave 60 different witnesses in 120 orders, and lost the single-key input's signature in 96 of them ([X3a](experiments/X3a/results.md)).
- **The envelope repeats the multisig script** that the witness already carries.

C keeps D's exact-length lock for the final witness only.

## B: a PSBT-style format, per input (not chosen; 74 as B+w)

**The idea.** Global and per-input maps as in Bitcoin's BIP-174: the raw transaction, a previous transaction and a multisig config per input, and partial signatures per input.

**What the evidence showed:**
- **B as designed carries no witnesses**, so with a witness beyond the inputs its readers compute the wrong message and neither real signature verifies (case S9); its round trip onto the building-packet profile fails there too ([X2](experiments/X2/results.md#1-round-trips)). With the witness templates added (B+w) it passes every case.
- **Its per-input layout repeats a shared previous transaction:** PR #34 is 1,300,648 bytes as B against 733,078 as C, because both inputs spend one 284,008-byte transaction ([X2](experiments/X2/results.md#2-bytes-zlib-level-9-in-brackets)).
- **Its format layer is larger:** 98 code lines plus 77 of Molecule decoding, against C's 63 ([X6 §4](experiments/X6/results.md#4-what-path-a-adds-on-top-of-c-measured-in-ccc-and-how-b-compares)).
- **Its merge rule had to change.** BIP-174's Combiner may "pick arbitrarily when conflicts occur", and with a member's high-s twin (which the lock accepts) that gave different results in 715 of 2,000 trials; PCZT's strict rule failed in 1,531 ([X3a](experiments/X3a/results.md)).
- **Its network id isn't signed,** so it protects nothing ([X4](experiments/X4/results.md#2-each-attack-in-each-format), attack 6c).

Its adoption and phase 1 scores are provisional: it wasn't patched into a wallet. It would pass C only if both scored 5, above C's own measured 4 ([scoreboard](scoreboard.md)).

## A: CoBuild's building packet as the exchange format (kept as C's mapping target)

**The idea.** Use a profile of CoBuild's `BuildingPacketV1`: the transaction as `payload`, the input cells as `resolved_inputs`, and each multisig group's config, signatures and previous transactions in a `lock_actions` entry, as a 2024 proof of concept did ([background §11](background.md#11-prior-art-on-ckb)).

**Why it isn't the exchange format:**
- **More code even in CCC,** which already has Molecule tools and a `BuildingPacket` codec: +95 code lines on top of C. ckb-cli and Neuron have no CoBuild code, and the Rust types alone are 5,200 generated lines in cryptape's proof of concept ([X6 §4](experiments/X6/results.md#4-what-path-a-adds-on-top-of-c-measured-in-ccc-and-how-b-compares)).
- **A CoBuild reader that doesn't know the profile trusts `resolved_inputs`,** and would show a fee of 1,000,000.00001186 CKB for a real 0.00001186 ([X4](experiments/X4/results.md#2-each-attack-in-each-format), attack 1b).
- **CoBuild's own signing message isn't the legacy lock's,** and CoBuild is deferred or prerelease in the three wallets ([background §8](background.md#8-cobuild-and-otx)).

**What it gives the design:** a binary view about half of C's size uncompressed (367,378 bytes for PR #34), and the profile C maps onto losslessly, so a CoBuild tool can carry a Sigsheet ([X2 §3](experiments/X2/results.md#3-c4-c-maps-losslessly-onto-the-building-packet-profile)).

## E: gathering over a relay or P2P (an optional transport, later)

**The idea.** Signers post their signatures to a relay (for example Nostr) and anyone collects them, on top of whichever format wins.

**Why not for the first version:**
- **A whole PR #34 file (733,078 bytes) is larger than every relay message limit seen:** 16,384, 65,535 and 524,288 bytes ([X7 §3](experiments/X7/results.md#3-limits)). One signature with the ids that place it is 367 bytes and fits them all.
- **A relay can drop or delay events undetectably,** and it needs infrastructure and a separate host key.
- **Even with every provisional score at the maximum it reaches 69,** below passing files along (70) ([scoreboard](scoreboard.md#ways-of-gathering-g2-on-top-of-a-format)).

It passes the gates as a layer over the format, so it stays an optional transport for v0.2 ([design record §9](design-record.md#9-later-versions)).

## F: on-chain gathering in signature cells (not chosen)

**The idea.** Each signer posts their signature in a cell on chain; anyone assembles the final transaction from those cells.

**Why not:**
- **About 182 CKB locked per posted signature** (a signature cell's occupied capacity) and **two fees per signer**.
- **Pending signatures are public before execution**, and an offline signer needs someone online to post for them.
- **The deploy transaction itself can't be hosted on chain** within CKB's block limits, so off-chain transport is still needed.

It passes the gates only for small, non-contending cases, and scores 24 of 75 ([scoreboard](scoreboard.md#ways-of-gathering-g2-on-top-of-a-format)).

## G: threshold signatures (dropped)

**The idea.** Signers run a threshold scheme (FROST, MuSig2 or threshold ECDSA) and produce one combined signature.

**Why it fails C1 and C3:**
- The existing lock needs M recoverable ECDSA signatures from M distinct members, each matching one of the N key hashes the address fixes ([background §1](background.md#1-the-multisig-lock)).
- FROST and MuSig2 produce Schnorr signatures, and threshold ECDSA one signature under one new group key, which no existing address lists ([background §14](background.md#14-security-lessons)). So a threshold scheme can't spend an existing multisig address: using one means new keys and a new address.
- Threshold schemes also change how keys are held and how signing works, which C3 rules out.

## Other alternatives

- **A converter between today's formats:** it adapts to each tool's format, which is a middle-layer bridge, so it fails G1.
- **Reusing CKB IDL for the multisig witness:** CKB IDL 0.1.0 can't describe the witness in general, no IDL can be verified for the deployed locks, and reuse would add code rather than remove it ([XC4](experiments/XC4/results.md); [design record §6.2](design-record.md#62-ckb-idl-complements-ckb-idl-instead-of-duplicating-it-c4)).
