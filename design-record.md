# Sigsheet: the design record

Sigsheet is an open format, with rules, for a CKB transaction that several people sign. ckb-cli, Neuron, CCC and other tools all read the same file and add their signatures to it directly.

This record states the problem the format solves, each design decision with its evidence, how the design is checked, its security analysis, phase 1's scope and acceptance tests, and the later versions.

**Every number here is design-stage.** It was measured on throwaway prototypes ([`experiments/prototypes/`](experiments/prototypes/README.md)) and on patched copies of the three wallets ([X6](experiments/X6/results.md)), on a local devnet with fresh test keys. No testnet or mainnet transaction was sent. Phase 1 builds the real implementations, and its acceptance tests (section 8) re-measure the design on them. To re-run the offline benchmarks yourself, run `./bench/run.sh` ([bench/README.md](bench/README.md)).

**How to read it.** Each claim links to its evidence: an experiment's results in this repository, a permalink to source code at a pinned commit, an RFC, or a public post. The pinned commits are listed in [sources.md](sources.md). Background facts about CKB's multisig lock and today's wallets are in [background.md](background.md), each with its source. A claim that no evidence settles is marked **open**, and no open claim decides anything here. What maintainers or teams might do is stated only from their public statements.

## 1. The problem

### 1.1 Who has it, and how badly

CKB multisigs hold shared money and upgrade contracts. Their signers today sign in their own tools, and then one person gathers the signatures, puts exactly M of them into one file and sends the transaction.

- **Contract upgrades.** fiber-scripts PR #34 upgraded mainnet contracts with a 3-of-5 multisig. The deployer opened the PR with ckb-cli's deploy file and their own signature, and asked each signer to run `ckb-cli deploy sign-txs` and post the output as a comment. Four signers pasted their signatures as PR comments ([comment 1](https://github.com/nervosnetwork/fiber-scripts/pull/34#issuecomment-6571892250), [2](https://github.com/nervosnetwork/fiber-scripts/pull/34#issuecomment-6573354672), [3](https://github.com/nervosnetwork/fiber-scripts/pull/34#issuecomment-6581601897), [4](https://github.com/nervosnetwork/fiber-scripts/pull/34#issuecomment-6605978601)). Then one person copied three of them into the deploy file by hand and sent it ([X1](experiments/X1/results.md) replays every step from the real files).
  - The PR was opened at 07:22:37 UTC on 2026-11-02 ([PR #34](https://github.com/nervosnetwork/fiber-scripts/pull/34)).
  - The threshold of three was reached at 09:13:05 UTC the same day ([the third signature](https://github.com/nervosnetwork/fiber-scripts/pull/34#issuecomment-6573354672)).
  - The transaction committed on 2026-11-09 at 03:16:08 UTC, in block 20,965,430, about 6 days 18 hours after the PR opened ([X1](experiments/X1/results.md#real-signatures)).
- **The tools don't interoperate** ([X1](experiments/X1/results.md#interoperability-findings)):
  - Neuron's import of a ckb-cli file drops the signatures;
  - CCC reads Neuron's file but empties its partly signed witness;
  - ckb-cli has no reader for Neuron's file;
  - ckb-cli and Neuron can't sign the 2024 multisig deployment, which holds 5,884,417.54 CKB on mainnet ([background §3](background.md#3-the-three-multisig-deployments)).
- **Developers have described it.**
  - A ckb-cli maintainer asked for a `request-signature` command that would "Generate the tx json file and a markdown guidance for signers" and support "sending request to ckb-cli and Neuron users" ([ckb-cli#603](https://github.com/nervosnetwork/ckb-cli/issues/603)).
  - The same maintainer reported that "`ckb-cli` saves the signature, and `Neuron` saves the pub key hash and stores the signatures in witnesses" ([ckb-cli#584](https://github.com/nervosnetwork/ckb-cli/issues/584)), and wrote "It's frustrated that `sign-txs` does not tell how to use the generated signatures, and it's format is not consistent with the info file" ([ckb-cli#569](https://github.com/nervosnetwork/ckb-cli/issues/569)).
  - A deployer of another mainnet script wrote that ckb-cli's multisig file behaviour "is very confused to me" ([ckb-cli#658](https://github.com/nervosnetwork/ckb-cli/issues/658)).
  - CKB's DevRel lead wrote: "I have recently been thinking about using a P2P network to enable a multisignature wallet to manage on-chain assets" ([t/10794/5](https://talk.nervos.org/t/10794/5)).

**What the record doesn't show** is why the wait was long. PR #34 reached its threshold in under two hours and took about six days more to reach the chain, so the slow part may be review or scheduling rather than gathering (section 10, item 3).

### 1.2 The goal

**Sigsheet's goal is a unified multisig signature format that ckb-cli, Neuron, CCC and other tools adopt, so that signatures are interoperable without a middle-layer bridging tool, and no one has to collect all signatures and forward them for aggregation.**

The design is checked against these requirements (gates). A design that fails one is dropped.

| Gate | Requirement |
|---|---|
| **G1** | Signatures work across tools with no bridge in the middle |
| **G2** | Signatures are gathered without one person collecting and forwarding them |
| **C1** | It works with the existing multisig lock scripts (the genesis, 2024 and v2 deployments) and with addresses that already exist. No new on-chain script |
| **C2** | A signer can check everything before signing, offline, from the file alone; any check that needs the signer's own node is named, with the reason |
| **C3** | It's tool-neutral: implementable in ckb-cli (Rust), Neuron (TypeScript, Electron) and CCC (TypeScript), without changing how each tool holds keys or signs |
| **C4** | It builds on CoBuild where CoBuild fits, and complements CKB IDL instead of duplicating it |
| **C5** | Phase 1 stands on its own: complete and usable. Later versions only broaden it |

**What the design doesn't change.** Each signer still receives the file and sends their copy on. The design removes the collector and the hand-trimming of signatures to exactly M; it doesn't automate delivery. An optional relay could do that in a later version (section 9).

## 2. The design in short

**The design is path C, one canonical JSON file per transaction, with path D merged in** ([paths.md](paths.md)). The file carries the transaction, a proof of every input, the multisig configs and every signature so far, keyed by lock group and signer.

On the design-stage measurements it meets every gate:
1. **G1 and G2 hold end to end.** ckb-cli, CCC and Neuron, each patched and each signing with its own code, signed one shared file in seven devnet flows. The file was passed along, or copies were posted and merged by anyone, with no collector, and all seven transactions committed ([X5](experiments/X5/results.md)). In two more committed flows the wallets created the file themselves ([XRT-4](experiments/XRT/results.md#xrt-4-creating-the-file-inside-the-wallets)).
2. **Adoption is small and leaves each wallet's code intact.** Reading, signing, merging and finalizing took 381 code lines in ckb-cli, 229 in CCC and 137 in Neuron; creating took 87 in ckb-cli and 52 in CCC. Every wallet's own tests gave the same results before and after ([X6](experiments/X6/results.md), [XRT-4](experiments/XRT/results.md#xrt-4-creating-the-file-inside-the-wallets)). These counts are for the design's first version: the rules added after the attacks in section 5 (Nervos DAO inclusion proofs, token display, refusing conflicting entries) were tested on the prototypes only, so phase 1's patches will be larger.
3. **Safety rests on four offline checks:** previous transactions by hash, the config by hash, signatures by the lock's own message and membership, and a deterministic merge. They catch every attack tested ([X4](experiments/X4/results.md)), and the merge gives the same bytes in any order: 3,150 of 3,150 trials ([X3](experiments/X3/results.md)).

**Scores** ([scoreboard.md](scoreboard.md)): of 100, format C 84, B+w 74, A 64; of 75, gathering through the file itself 70, a relay (E) 41, on-chain signature cells (F) 24.

## 3. The design decisions, with their evidence

| # | Decision | Evidence |
|---|---|---|
| D1 | **One canonical JSON file**, seven top-level fields: `version`, `transaction`, `context`, `headers`, `inclusion_proofs`, `multisig_configs`, `signatures`; nothing else | [X2](experiments/X2/results.md#1-round-trips): 12 of 12 cases lossless and canonical; [X6 §3](experiments/X6/results.md#3-the-three-patches-read-and-write-the-same-bytes): ckb-cli and CCC write identical bytes |
| D2 | **RFC 8785 canonical form, hex strings, Molecule hex witnesses, `"type": null` for an absent type script.** A reader re-encodes the parsed file and refuses it on any byte difference, before anything is dropped | [X2](experiments/X2/results.md#1-round-trips); [X6 §3](experiments/X6/results.md#3-the-three-patches-read-and-write-the-same-bytes) (CCC leaves out an absent `type`; the spec fixes one form); [XRT-2](experiments/XRT/results.md#xrt-2-prototype-checks-no-chain) (the canonical check comes first) |
| D3 | **Witness templates:** each signed group's first witness without its lock; every other witness kept exactly. A template must be `0x` or a canonical `WitnessArgs` | The lock's message covers the group's other witnesses and every witness beyond the inputs ([background §1](background.md#1-the-multisig-lock)); B without witnesses fails case S9 ([X2](experiments/X2/results.md#1-round-trips)); a template with a fourth field was accepted before this rule ([XRT-2](experiments/XRT/results.md#xrt-2-prototype-checks-no-chain)) |
| D4 | **Previous transactions, raw part only, keyed by hash,** one per transaction | The message doesn't cover the input cells ([background §1](background.md#1-the-multisig-lock)); the hash covers only the raw transaction ([background §2](background.md#2-transaction-structure-and-hash), [X2a](experiments/X2a/results.md)); a falsified input is refused ([X4](experiments/X4/results.md#2-each-attack-in-each-format), attack 1) |
| D5 | **Headers for every header dep, keyed by hash, and inclusion proofs for Nervos DAO withdrawals.** A DAO withdrawal's fee counts each withdrawing input at its maximum withdrawable capacity. The withdrawing block is taken only from an inclusion proof (CKB's transaction proof, verified offline against a carried header). Without a proof, the fee is shown as an upper bound ("at most"), never lowered | In a DAO withdrawal "the sum of all output cells' capacity might exceed the sum of all input cells' capacity", and the withdrawable amount comes from the deposit and withdrawing headers ([RFC 0023 L44](https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0023-dao-deposit-withdraw/0023-dao-deposit-withdraw.md#L44), [L128-L134](https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0023-dao-deposit-withdraw/0023-dao-deposit-withdraw.md#L128-L134)); the DAO script finds the withdrawing block from the chain, by the input ([dao.c L197](https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c#L197)); on the devnet, two deposits withdrawn together: the node's fee 0.001 CKB, the proofs exactly 0.001, an upper bound from the other headers 4.636 ([XRTb-3](experiments/XRTb/results.md#xrtb-3-a-nervos-dao-withdrawal-of-two-deposits)) |
| D6 | **Multisig configs keyed by `blake160(script)`, checked against the lock args;** no code hash, hash type or since. A config listing one key twice is refused, as ckb-sdk refuses it. A config whose key occurs in no input's lock args is refused | ckb-cli PR #652 makes ckb-cli "detect multisig type (Legacy/V2) from actual input cell locks instead of deployment config" ([PR #652](https://github.com/nervosnetwork/ckb-cli/pull/652)); a swapped config is refused ([X4](experiments/X4/results.md#2-each-attack-in-each-format), attack 7); a repeated key ([XRT-1](experiments/XRT/results.md#xrt-1-which-valid-signature-sets-each-deployed-binary-accepts)); 50 configs for no input took a file from 2,685 to 14,585 bytes with the same unsigned id ([XRTb-2](experiments/XRTb/results.md#xrtb-2-the-simpler-rules-against-the-design-rules-offline)) |
| D7 | **Signatures keyed by lock group (lock script hash) and signer** | Keyed by lock args, two groups that share a multisig script under two deployments mix their signatures ([X3 §2](experiments/X3/results.md#2-signatures-must-be-keyed-by-lock-group-not-by-lock-args-s10)); [X3a](experiments/X3a/results.md) |
| D8 | **The lock kind comes only from the input cell's code hash and hash type.** Version 1 signs the single-key lock (20-byte args, as the lock requires) and the three multisig deployments | The deployments ([background §3](background.md#3-the-three-multisig-deployments)); the single-key lock checks `args_bytes_seg.size != BLAKE160_SIZE` ([sighash_all.c L106](https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/secp256k1_blake160_sighash_all.c#L106)); a 32-byte-args input was accepted before this rule ([XRTb-2](experiments/XRTb/results.md#xrtb-2-the-simpler-rules-against-the-design-rules-offline)); the message reads only the transaction, the previous transactions and the config ([X2 §4](experiments/X2/results.md#4-the-ckb-idl-boundary-what-a-signers-message-computation-reads)) |
| D9 | **The message is the lock's own rule,** computed from the file | 15 lock groups agree byte for byte across CCC, ckb-cli, ckb-sdk and an independent implementation ([X1](experiments/X1/results.md)); computed from the file alone in 12 of 12 cases ([X2](experiments/X2/results.md#1-round-trips)) |
| D10 | **Show only derived data:** the outputs with each output's data hash; the inputs with each input's data hash; the fee (DAO-aware, D5); each group and its members; the network, from known cell deps, otherwise "unknown". An output with no type and no data whose lock is some input's is labelled as going back to that input's lock; any other output is a payment. The amounts of known tokens (xUDT, sUDT) in and out, and a warning when an input's type script appears on no output | Display fields are attack surfaces ([X4](experiments/X4/results.md#2-each-attack-in-each-format), attack 9); a type script runs again when its cell is spent: "And the code is also executed when the cell is destroyed" ([RFC 0022 L217](https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0022-transaction-structure/0022-transaction-structure.md#L217)); a 1,000,000-unit xUDT cell consumed was shown only as "fee: 0.001 CKB" before this rule ([XRTb-2](experiments/XRTb/results.md#xrtb-2-the-simpler-rules-against-the-design-rules-offline)) |
| D11 | **Merge:** only files the reader accepts; the same unsigned transaction; verify (membership first), members only, low-s, the smaller bytes on a conflict, keep signatures beyond M; keep only the context entries some input spends; carry other lock kinds' signatures unverified; two different entries under one signer in a group the reader doesn't sign refuse the merge | 2,000 of 2,000 trials agree, where BIP-174's and PCZT's rules fail ([X3a](experiments/X3a/results.md)); 3,150 of 3,150 ([X3](experiments/X3/results.md)); the lock accepts a high-s twin on chain ([X4 §1](experiments/X4/results.md#1-the-lock-accepts-a-malleated-signature-on-all-three-deployments-run-on-chain)); membership first: 20,000 junk entries read in 0.022 s instead of 106.49 s ([XRT-2](experiments/XRT/results.md#xrt-2-prototype-checks-no-chain)); carrying another group's signature ([XRT-3](experiments/XRT/results.md#xrt-3-a-lock-the-reader-doesnt-sign)); a zero-byte entry replaced a valid signature under the "smaller bytes" rule in a group the reader doesn't sign ([XRTb-2](experiments/XRTb/results.md#xrtb-2-the-simpler-rules-against-the-design-rules-offline)) |
| D12 | **Ready and finalize:** the first R members, then the lowest member positions, in member order; exactly `4 + 20N + 65M` bytes; anyone may finalize. **Genesis groups** skip the positions the genesis binary rejects (position 10 only when M ≤ 10, position 18 only when M = 1, so a required member is never skipped, since R ≤ M) and are checked with a node for N > 10 when sent. A group whose only usable sets need a skipped member isn't ready until another member signs. **Partial finalize** when other locks are present | The lock's layout ([background §1](background.md#1-the-multisig-lock)); [X5](experiments/X5/results.md) F6 (R = 1); the genesis binary's rejected sets ([XRT-1](experiments/XRT/results.md#xrt-1-which-valid-signature-sets-each-deployed-binary-accepts), [XRTb-1](experiments/XRTb/results.md#xrtb-1-the-genesis-binary-with-a-required-member-and-a-set-no-order-fixes)); partial finalize, committed ([XRT-3](experiments/XRT/results.md#xrt-3-a-lock-the-reader-doesnt-sign)) |
| D13 | **Gathering:** the file is passed along, or copies are posted and merged by anyone; no collector role; a relay is optional and later | [X5](experiments/X5/results.md); [X7](experiments/X7/results.md#3-limits) (relay limits); [scoreboard](scoreboard.md#ways-of-gathering-g2-on-top-of-a-format) |
| D14 | **Creation inside each wallet:** the one step that needs a node. It fetches each input's previous transaction, and the inclusion proofs (`get_transaction_proof`) for Nervos DAO withdrawing inputs | [XRT-4](experiments/XRT/results.md#xrt-4-creating-the-file-inside-the-wallets): ckb-cli and CCC create byte-identical files; both flows committed |
| D15 | **Each wallet signs with its own signer;** no new witness-layout code | [X6 §1](experiments/X6/results.md#1-path-c-in-each-wallet-the-patch-its-hook-points-its-size) |
| D16 | **CoBuild:** a lossless profile of `BuildingPacketV1`, stated in the spec | [X2 §3](experiments/X2/results.md#3-c4-c-maps-losslessly-onto-the-building-packet-profile); [X6 §4](experiments/X6/results.md#4-what-path-a-adds-on-top-of-c-measured-in-ccc-and-how-b-compares); section 6 |
| D17 | **CKB IDL:** no signing-rule field; a later lock kind takes its signing description from CKB IDL if CKB IDL defines one | [XC4](experiments/XC4/results.md); [X2 §4](experiments/X2/results.md#4-the-ckb-idl-boundary-what-a-signers-message-computation-reads); [X6 §5](experiments/X6/results.md#5-the-ckb-idl-reuse-alternative-where-it-can-be-measured); section 6 |
| D18 | **Versions and extension:** a new lock kind needs no new field and no version change. Its definition states its code hashes, where its config key sits in its args, how its witness carries the multisig bytes, and its message rule. A new field changes `version` | An Omnilock multisig-mode group was carried and its config kept; its key sits at args bytes 1-20 (`<identity, 21 bytes> <omni_lock args>`, [omni_lock.c L138](https://github.com/nervosnetwork/omnilock/blob/280dd97ac0930ea1ed766a18d49478229347c832/c/omni_lock.c#L138); [XRTb-2](experiments/XRTb/results.md#xrtb-2-the-simpler-rules-against-the-design-rules-offline)); carrying a group a reader doesn't sign ([XRT-3](experiments/XRT/results.md#xrt-3-a-lock-the-reader-doesnt-sign)); PSBT's lessons: new fields without a version change, because older software ignores unknown fields ([background §13](background.md#13-other-ecosystems)) |
| D19 | **Hardware wallets:** the file carries what Neuron's Ledger path sends | [XQ14](experiments/XQ14/results.md) |

### 3.1 The file, field by field

| Field | What it holds | How a reader checks it |
|---|---|---|
| `version` | `"0x1"` | Readers refuse a version they don't know |
| `transaction` | The transaction in CKB RPC JSON (hex numbers), with the witness templates (D3) | The unsigned id is the transaction hash together with the witness templates; files for different unsigned ids don't merge |
| `context` | `{transaction hash: raw previous transaction}`, one per transaction an input spends from | Each entry must hash to its key; every input's out point must find its entry; an entry no input spends is refused |
| `headers` | `{block hash: header}`, one per header dep | Each header must hash to its key |
| `inclusion_proofs` | `{transaction hash: CKB transaction proof}` for the previous transactions of Nervos DAO withdrawing inputs; empty when unused | The proof must verify against a carried header's `transactions_root` |
| `multisig_configs` | `{blake160(multisig script): {require_first_n, threshold, public_key_hashes}}` | Each config must hash to its key; its key must occur in some input's lock args; no key may repeat |
| `signatures` | `{lock script hash: {signer key hash: 65-byte signature}}` | Each signature is verified against the group's message, recovers to its signer, the signer is a member; normalized to low-s |

## 4. How the design is checked

### 4.1 The experiments

Every experiment has a README with the exact commands and a results page that opens with its conditions. All numbers, with their conditions: [numbers.md](numbers.md).

| Experiment | What it checks | Result (design-stage) |
|---|---|---|
| [X1](experiments/X1/results.md) | Every tool computes the same signing message | CCC 1.23.1, ckb-cli 2.0.0, ckb-sdk 5.0.0 and an independent implementation agree byte for byte on 15 lock groups (2 real cases, 10 devnet cases); Neuron v0.204.1 leaves out witnesses beyond the inputs (12 of 13). Every real signature verifies; 9 mixed-tool devnet transactions committed |
| [X2](experiments/X2/results.md) | Each format round-trips; the CoBuild mapping; what a signer reads | C: 12 of 12 lossless and canonical, 32 of 32 signatures verified from the file alone; C ↔ A byte-identical on 12 of 12 each way; the message reads only the transaction, the previous transactions and the config |
| [X2a](experiments/X2a/results.md) | The bytes of the real cases | Hex JSON is ×2.001 the binary size for PR #34 |
| [X3](experiments/X3/results.md) | Merging is safe in any order | 3,150 of 3,150 trials give the same bytes (six cases, three formats), idempotent, junk-free; keyed by lock args, two groups sharing args mix their signatures |
| [X3a](experiments/X3a/results.md) | Which merge rule is order-independent | CCC's in-witness merge: 60 different witnesses from 120 orders; the design's rule: 2,000 of 2,000 trials agree |
| [X4](experiments/X4/results.md) | Each attack is caught | Every attack caught in C, B+w and A; the lock accepts a malleated high-s twin on chain on all three deployments; replay rejected on the devnet |
| [X5](experiments/X5/results.md) | G1 and G2 end to end | Seven flows, three wallets, no collector, all committed |
| [X6](experiments/X6/results.md) | What adoption costs | ckb-cli +415 lines (381 code), CCC +260 (229), Neuron +153 / −2 (137); own tests unchanged; path A adds 95 code lines in CCC; CKB IDL reuse adds 29 crates to ckb-cli |
| [X7](experiments/X7/results.md) | Sizes, times, limits | Sizes 2,371 bytes (the genesis 2-of-3 payment) to 733,078 (PR #34); ckb-cli merges PR #34 in 0.10 s, CCC in 1.86 s; the final PR #34 transaction is 81,889 bytes against a 512,000-byte pool limit |
| [XC4](experiments/XC4/results.md) | Can CKB IDL describe and bind the multisig witness; what reuse costs | 0 of 13 real locks decode with the natural description; an 18,372-byte union covers N ≤ 5; no deployed code cell can be bound; an IDL client is 1,318 Rust code lines, and none exists in TypeScript |
| [XQ14](experiments/XQ14/results.md) | A Ledger, on Ledger's emulator | The Nervos app 0.6.3 signed a 2-of-3 genesis multisig built from the file, committed; the same device bytes from every format; the app's own limits (section 5.7) |
| [XRT](experiments/XRT/results.md) | Attacks and objections, first round | The genesis binary rejects valid sets when position 10 signs with M ≤ 10, and position 18 with M = 1; a lock the reader doesn't sign, carried and finalized, committed twice; creation in ckb-cli and CCC, committed twice |
| [XRTb](experiments/XRTb/results.md) | Attacks and objections, second round | Two Nervos DAO deposits withdrawn in one transaction, committed: the node's fee 0.001 CKB, an upper bound from the headers 4.636, inclusion proofs exactly 0.001; a required genesis member at position 10 accepted (M = R = 11); the "smaller bytes" rule let junk replace a valid signature, and the design refuses that merge |

### 4.2 The scoring

Designs that pass every gate are scored 0-5 on seven criteria, weighted: security 25, adoption cost in each wallet 20, fit with CoBuild and CKB IDL 15, offline completeness 10, simplicity 10, extensibility 10, phase 1 fit 10. A criterion's points are its weight × score / 5. The scores and their reasons are in [scoreboard.md](scoreboard.md).

How much the choice depends on provisional scores:
- C's scores are measured, except extensibility, which is untested and equal (4) for all three formats.
- B+w's adoption and phase 1 fit are provisional (it wasn't patched into a wallet). B+w would pass C only if both scored 5, above C's own measured 4 (B+w would then have 86). The prototypes point the other way: B's format layer is 98 code lines plus 77 of Molecule decoding, against C's 63.
- E stays below gathering in the format even with every provisional score at its maximum (69 against 70).

## 5. Security analysis

### 5.1 The root, and the checks that answer it

The multisig message covers the transaction hash and the witnesses, **not the input cells** ([background §1](background.md#1-the-multisig-lock)). A signer that trusts an input amount it can't check can be robbed through the fee, as Bitcoin's hardware wallets were before they required full previous transactions (CVE-2020-14199, [background §14](background.md#14-security-lessons)). Every check below runs offline, from the file alone, unless marked.

### 5.2 Attacks considered and how the design answers them

| Attack | What stops it | Measured (design-stage) |
|---|---|---|
| Falsified input cells (the fee attack) | Each previous transaction must hash to its input's out point | [X4](experiments/X4/results.md#2-each-attack-in-each-format) attack 1: refused |
| A Nervos DAO withdrawal hiding its fee | The headers are carried and checked by hash; the fee counts each DAO input at its maximum withdrawable capacity, with the withdrawing block taken only from a verified inclusion proof, and otherwise shown as an upper bound | [XRTb-3](experiments/XRTb/results.md#xrtb-3-a-nervos-dao-withdrawal-of-two-deposits): inputs − outputs showed −7.125 CKB; the proofs gave the node's 0.001 CKB, and the node's 7.12722788 CKB when the output was cut to the deposits, where inputs − outputs showed 0.001 |
| A swapped transaction, altered outputs or fees | Signatures are checked against the file's own message; files for different transactions don't merge | [X4](experiments/X4/results.md#2-each-attack-in-each-format) attacks 2-3 |
| Signatures from non-members | The recovered key must be a member; membership is checked before recovery | [X4](experiments/X4/results.md#2-each-attack-in-each-format) attack 4; [XRT-2](experiments/XRT/results.md#xrt-2-prototype-checks-no-chain): 20,000 junk entries, 106.49 s to read without the early check, 0.022 s with it |
| Junk that blocks finalizing | Verify, members only, low-s, key by signer, the smaller bytes on a conflict | [X4](experiments/X4/results.md#2-each-attack-in-each-format) attack 5 (still finalizes); [X3](experiments/X3/results.md) (3,150 of 3,150) |
| A swapped multisig config | The config must hash to the lock args | [X4](experiments/X4/results.md#2-each-attack-in-each-format) attack 7 |
| A changed covered witness | The message covers it | [X4](experiments/X4/results.md#2-each-attack-in-each-format) attack 10 |
| Display fields (a description, a CoBuild message, a change index) | The schema has none; readers refuse them | [X4](experiments/X4/results.md#2-each-attack-in-each-format) attack 9 |
| Replay | Out points can't be spent twice; old signatures don't fit a new transaction | [X4](experiments/X4/results.md#2-each-attack-in-each-format): both rejected on the devnet |
| Replay across networks | A signature covers the transaction hash, which covers every input's out point; the networks' genesis transactions differ, so no out point exists on both | Rule; [X4](experiments/X4/results.md#2-each-attack-in-each-format) attack 6b (a signature moved to another transaction fails with -52) |
| A code deployment with a swapped binary | Each output's data hash is shown, to compare with the release | Rule (D10) |
| A type script hiding in "change" | "Back to an input's lock" only with no type and no data | Rule (D10); [RFC 0022 L217](https://github.com/nervosnetwork/rfcs/blob/0c945451c24194f4d34d81195c0159df0a67581a/rfcs/0022-transaction-structure/0022-transaction-structure.md#L217) |
| Junk filed under a member in a group the reader doesn't sign | Two different entries under one signer refuse the merge; a reader that signs the kind resolves it by verifying | [XRTb-2](experiments/XRTb/results.md#xrtb-2-the-simpler-rules-against-the-design-rules-offline): under the "smaller bytes" rule, 65 zero bytes replaced a valid signature, in both orders |
| Configs for no input, to bloat every merged copy | A config is refused unless its key occurs in some input's lock args | [XRTb-2](experiments/XRTb/results.md#xrtb-2-the-simpler-rules-against-the-design-rules-offline): 50 such configs, 2,685 → 14,585 bytes, the same unsigned id |
| Tokens consumed by a transaction that shows only CKB | Each input's data, the amounts of known tokens in and out, and a warning when a type script leaves | [XRTb-2](experiments/XRTb/results.md#xrtb-2-the-simpler-rules-against-the-design-rules-offline): a 1,000,000-unit xUDT cell consumed was shown as "fee: 0.001 CKB" without these rules |
| One out point listed twice | Duplicate inputs are refused | [XRT-2](experiments/XRT/results.md#xrt-2-prototype-checks-no-chain): accepted before this rule, with a fee shown 1,000.001 CKB too high |
| A since the genesis or 2024 lock will reject | The since warning follows each deployment's own rule | [XRT-3](experiments/XRT/results.md#xrt-3-a-lock-the-reader-doesnt-sign) part C |

**What needs the signer's node** (C2 asks for the exact list): creating the file (the previous transactions, headers and inclusion proofs come from the chain); whether the inputs are still unspent; whether the cell deps and type scripts will validate; and, for a `data1` lock whose code comes from a cell the wallet doesn't know, which network the inputs are on. None of these can move value if it fails: the transaction fails on chain. For a genesis multisig with N > 10, the finalizer also checks its choice with a node (5.5).

### 5.3 Objections considered and how the design answers them

| Objection | Answer | Evidence |
|---|---|---|
| A transaction with a lock the reader doesn't sign can't be finalized | Partial finalize: a reader finalizes the groups it signs and leaves the others' witnesses as in the template | [XRT-3](experiments/XRT/results.md#xrt-3-a-lock-the-reader-doesnt-sign): committed |
| A strict schema drops other lock kinds' signatures, so later lock kinds break version 1 readers | Signatures under a group of a kind the reader doesn't sign are kept unchanged and unverified (at most 255 per group) | [XRT-3](experiments/XRT/results.md#xrt-3-a-lock-the-reader-doesnt-sign) B: a later reader finalized, committed |
| The wallets can't create the file, so a bridge is needed | Creation is part of each wallet's change | [XRT-4](experiments/XRT/results.md#xrt-4-creating-the-file-inside-the-wallets): ckb-cli +87 code lines, CCC 52; both committed |
| The genesis binary rejects a set with a member at position ≥ M | Not as stated (a 2-of-3 signed by members 1 and 2 committed), but it does reject some valid sets; the finalize rule skips those positions | [XRT-1](experiments/XRT/results.md#xrt-1-which-valid-signature-sets-each-deployed-binary-accepts); [X5](experiments/X5/results.md) F3 |
| Skipping positions 10 and 18 would skip a required member | It can't: the skip applies only when M ≤ 10 (position 10) or M = 1 (position 18), and R ≤ M | [XRTb-1](experiments/XRTb/results.md#xrtb-1-the-genesis-binary-with-a-required-member-and-a-set-no-order-fixes): M = R = 11 accepted in both orders |
| A config that lists one key twice is refused, so existing addresses fail C1 | A stated limit, not a C1 failure: ckb-sdk refuses such configs too, and such an address is controlled by the repeated key alone | [XRT-1](experiments/XRT/results.md#xrt-1-which-valid-signature-sets-each-deployed-binary-accepts): spent by one key and its high-s twin |
| An offline signer can't tell the network | When it can't be derived, the reader says so and shows each lock as its script, with both address forms labelled; a declared network field is a claim no reader can check | Rule (D10) |
| An upper bound on a DAO fee misleads honest withdrawals of several deposits | The inclusion proofs give the exact fee; the bound is shown only without them, as "at most". A block hash that isn't proven is never used to lower the fee (design-stage: a rule measured on the prototypes, not yet in the wallets) | [XRTb-3](experiments/XRTb/results.md#xrtb-3-a-nervos-dao-withdrawal-of-two-deposits) |
| A DAO withdrawal can't be checked for maturity offline | The DAO script checks the since itself, so an immature withdrawal fails on chain and moves nothing ("Cell must at least be locked for one full lock period(180 epochs)", [dao.c](https://github.com/nervosnetwork/ckb-system-scripts/blob/72eb92fca090700dcb398cd8cad8fbd8bad40355/c/dao.c)); with the proofs, the minimal since is computed offline and equals the node's | [XRTb-3](experiments/XRTb/results.md#xrtb-3-a-nervos-dao-withdrawal-of-two-deposits) |
| Large files exceed relay limits and small devices' memory | Devices don't parse the JSON: the host sends a Ledger the bytes it needs. Any format that proves PR #34's inputs carries its 284,008-byte previous transaction | [XQ14](experiments/XQ14/results.md#2-size-is-not-the-limit-in-063); [X2a](experiments/X2a/results.md) |
| Hex JSON doubles the bytes | Measured and stated; a binary view (the CoBuild profile) exists where size matters | [X2a](experiments/X2a/results.md): ×2.001 for PR #34 |
| CCC's in-witness merge (path D's) is order-independent | It isn't: the same five files gave 60 different witnesses in 120 orders, and lost a single-key signature in 96 | [X3a](experiments/X3a/results.md) |
| The building packet's `resolved_inputs` proves the inputs | It doesn't: a CoBuild reader that trusts it would show a fee of 1,000,000.00001186 CKB for a real 0.00001186 | [X4](experiments/X4/results.md#2-each-attack-in-each-format) attack 1b |
| A network id in the file protects against replay | It isn't signed, so it protects nothing | [X4](experiments/X4/results.md#2-each-attack-in-each-format) attack 6c |

### 5.4 Merging when a member has two valid signatures

The lock accepts a signature's high-s twin: committed on all three deployments ([X4 §1](experiments/X4/results.md#1-the-lock-accepts-a-malleated-signature-on-all-three-deployments-run-on-chain)). So one member can have two valid byte strings for one message. Sigsheet's merge normalizes to low-s and keeps the smaller bytes: one result in any order, with junk, twins and repeats ([X3a](experiments/X3a/results.md): 2,000 of 2,000; [X3](experiments/X3/results.md): 3,150 of 3,150). BIP-174's "pick arbitrarily" differed in 715 of 2,000 trials, and PCZT's strict rule failed in 1,531 ([X3a](experiments/X3a/results.md)).

### 5.5 The genesis binary rejects some valid signature sets

The devnet's genesis multisig binary is byte-identical to mainnet's. On it, the node rejected valid sets in this pattern ([XRT-1](experiments/XRT/results.md#xrt-1-which-valid-signature-sets-each-deployed-binary-accepts)): written in member order, a set fails exactly when the member at position 10 (the 11th) signs and M ≤ 10, and when the member at position 18 signs and M = 1, for N up to 24. Written in descending order, more sets fail. The 2024 and v2 binaries accepted every set.

This matches a core developer's description of the genesis contract, "a bug that, under certain conditions, may fail to verify valid signatures" ([ckb#4788](https://github.com/nervosnetwork/ckb/issues/4788#issuecomment-2600748876)), and the 2024 fix, which sizes `used_signatures` by N instead of M ([background §3](background.md#3-the-three-multisig-deployments)). It affects every tool, not only Sigsheet. Sigsheet's finalize skips those positions for genesis groups, writes member order, and checks with a node for N > 10 (D12).

### 5.6 What a signer sees

A signer is shown only what it derives from checked data (D10): no free text and no unverified label. The incidents behind this rule: Bybit's and Radiant's signers approved what a compromised interface showed them ([background §14](background.md#14-security-lessons)). A signer still has to read the outputs: Sigsheet can show the true destination, amount, fee and code hash, but can't decide whether they are intended.

### 5.7 Hardware wallets

Tested on Ledger's emulator, Speculos ([XQ14](experiments/XQ14/results.md#4-the-emulator-friction-and-security)), with the emulator's own default test seed; no device and no real keys.

- **The emulator against a real device.** The emulator runs the Nervos app's own code, built from the release's source and SDK, so the app's logic, fixed buffers and screens are the device's. Speculos itself says "There is absolutely no guarantee that apps will have the same behavior on hardware devices and Speculos, though the differences are limited" ([Speculos README L71](https://github.com/LedgerHQ/speculos/blob/82fbd97a91ffcf1fbf9eb0201a95b70c09dfe921/README.md#L71)). **Open:** how long a real device takes to receive a long stream (PR #34's 2,826 APDUs), and whether its watchdog interrupts it. Neither depends on the format: every format sends the same bytes.
- **User friction**, the same under every format and the same as Neuron's Ledger path today: a 2-of-3 payment with change back to the multisig takes 11 screens; the change is shown as a second payment, and "Amount" counts it (999 CKB for a 500 CKB payment); a refused transaction makes the app quit without an error code.
- **Security:** the device hashes every previous transaction itself, so the amounts and fee it shows can't be falsified; it doesn't check that its own key is a member (Neuron checks that on the host); a format adds or removes no device-side risk.
- **The app's limits are those of Ledger's Nervos app 0.6.3, not of Sigsheet, and not a matter of size** (the emulator signed with up to 2 MB of previous transactions). The app refuses:
  - any v2 or 2024 multisig transaction, at any size, unless the user turns on "Allow sign hash", which signs blind;
  - a multisig input next to another input;
  - more than five outputs.

## 6. Fit with CoBuild and CKB IDL

### 6.1 CoBuild: "builds on CoBuild where CoBuild fits" (C4)

- **What CoBuild offers.** Its building packet is "the standard format for data exchange among parties during Transaction Co-build process", with multisig signing data in `lock_actions` ([t/7702/1](https://talk.nervos.org/t/7702/1)). A 2024 proof of concept used it for exactly this job ([background §11](background.md#11-prior-art-on-ckb)).
- **Why the design doesn't use it as the exchange format.**
  - CoBuild's own signing message differs from the legacy lock's, so the existing multisig lock can't use it ([background §8](background.md#8-cobuild-and-otx)).
  - Its `resolved_inputs` can't prove the input cells, and a reader that trusts them can be shown a false fee ([X4](experiments/X4/results.md#2-each-attack-in-each-format)).
  - Its status is deferred or prerelease: ckb-cli and Neuron have no CoBuild code; CCC's co-build prerelease defines no `BuildingPacket`; CCC's codec sits unused in `@ckb-ccc/spore` ([background §8](background.md#8-cobuild-and-otx)). CCC's maintainer reintroduced CoBuild only to simplify the Coin package ([t/10597/1](https://talk.nervos.org/t/10597/1), in Chinese).
- **How it builds on CoBuild anyway:** the format maps losslessly onto a profile of `BuildingPacketV1`, so a CoBuild tool can carry a Sigsheet and the reverse.
  - Measured: file → packet → file and packet → file → packet are byte-identical on 12 of 12 cases, with equal messages and signatures ([X2 §3](experiments/X2/results.md#3-c4-c-maps-losslessly-onto-the-building-packet-profile)).
  - A second implementation of the profile, in CCC (95 code lines), gives byte-identical packets on 12 of 12 ([X6 §4](experiments/X6/results.md#4-what-path-a-adds-on-top-of-c-measured-in-ccc-and-how-b-compares)).
  - The spec states that a Sigsheet carried as a building packet is safe only in tools that know the profile.

### 6.2 CKB IDL: "complements CKB IDL instead of duplicating it" (C4)

**The framing:** Sigsheet carries a partly signed multisig transaction between ckb-cli, Neuron, CCC and other tools; CKB IDL describes what a script's witness must contain.

**It holds:**
- **CKB IDL 0.1.0 can't describe the multisig witness in general** ([XC4](experiments/XC4/results.md)). A `vector` carries its own u32 count, while the lock keeps its counts in header bytes, so the natural description decodes 0 of 13 real locks. A union workaround covers every configuration up to N = 5 in an 18,372-byte document.
- **No IDL can be verified for the three deployed locks under CKB IDL's own rules:** none of their code cells ends in Binding Trailer 1, and none can be replaced (v2's `data1` code hash would change; the code cells are locked by zero locks). CKB IDL's own plan for legacy scripts ("legacy attestations", registry milestone M2) is future work and testnet-first ([XC4 §2](experiments/XC4/results.md#2-can-a-client-trust-any-such-document-for-the-existing-deployments-no)).
- **CKB IDL's only "signing metadata" is a per-script struct** outside the normative schema, which nothing uses: "Legacy signing metadata container" and "Signing metadata is not part of the normative IDL 0.1.0 document schema" ([types.rs L45-L47](https://github.com/ckb-idl/ckb-idl-client/blob/e7d8124921dc640018004a4a031fc6146535e334/src/types.rs#L45-L47)). "Partial-signing metadata" is deferred and undefined: "Signing and partial-signing metadata." ([ROADMAP.md L13](https://github.com/ckb-idl/ckb-idl-spec/blob/ebec1696b3df3336262c479650611bb344489f01/ROADMAP.md#L13)). CKB IDL calls itself "that complementary interface layer" to a PSBT-like portable workflow ([t/11031/1](https://talk.nervos.org/t/11031/1)).
- **Every Sigsheet field is one transaction's data; none describes a signing rule.** Logging every field the signer's message computation reads, in every format and case, it reads only the transaction, the previous transactions (and from them each spent lock's code hash, hash type and args) and the multisig config ([X2 §4](experiments/X2/results.md#4-the-ckb-idl-boundary-what-a-signers-message-computation-reads)).

**It's efficient:**
- Defining the layout in Sigsheet, by pointing to the lock's own rule, costs 0 extra bytes per file and 0 new lines of layout code: ckb-sdk, CCC and Neuron already have the multisig codec (125, 260 and 6 lines). Reusing CKB IDL would cost an 18,372-byte document per file, or a digest whose lookup needs a network (which breaks C2), plus an IDL client of 1,318 Rust code lines, with no TypeScript client ([XC4 §3](experiments/XC4/results.md#3-what-reuse-would-cost-against-defining-the-layout-in-sigsheet)).
- The Sigsheet code each wallet needs (137-381 code lines) is code for the file itself; none of it describes the witness layout. Adding `ckb-idl-client` 0.1.0 to ckb-cli adds 29 crate versions to its dependency graph (391 → 417) and replaces no code. In TypeScript it can't be done yet ([X6 §5](experiments/X6/results.md#5-the-ckb-idl-reuse-alternative-where-it-can-be-measured)).

**Open:** what CKB IDL's deferred "partial-signing metadata" will hold, which isn't written anywhere in its sources; and the TypeScript cost of reuse, which can't be measured until a TypeScript client exists (planned for CKB IDL's milestone M4).

**The design rule:** Sigsheet names each lock by the input cell's code hash and hash type and states the message rule of each lock kind it supports; the file carries no signing-rule field; a later lock kind takes its signing description from CKB IDL if CKB IDL defines one by then.

## 7. Adoption in each wallet

Measured at the pinned commits, with throwaway patches; the diffs are in [X6](experiments/X6/README.md).

| Wallet | Hook points (unchanged code the patch calls) | Patch | Own tests |
|---|---|---|---|
| **ckb-cli v2.0.0** (`80efc21`, Rust) | `tx_helper::build_signature` (its message rule); `SignerFn` from `get_privkey_signer` or `get_keystore_signer` (key file, keystore, plugin); ckb-sdk's `MultisigConfig::to_witness_data` | 3 files, +415 lines (381 code): `src/utils/sigsheet.rs` and `tx sigsheet-sign`, `sigsheet-merge`, `sigsheet-send` in `src/subcommands/tx.rs`; they run before ckb-cli's node check, so signing and merging work offline | `cargo test --locked`: 7 passed before and after |
| **CCC 1.23.1** (`7095cca`, TypeScript) | `SignerMultisigCkbPrivateKey.signOnlyTransaction`, `SignerMultisigCkbReadonly.getSignInfo`, `SignerCkbPrivateKey`, `Transaction.getSignHashInfo`, `MultisigCkbWitness`, `JsonRpcTransformers`, `recoverMessageSecp256k1`, the client cache (filled from the file) | 2 files, +260 (229 code): `ccc.Sigsheet` (read, sign, merge, finalize) | 759 of 759 before and after; `tsc --noEmit` clean |
| **Neuron v0.204.1** (`d3a7467`, TypeScript, Electron) | `TransactionSender.signMultisig` (its own signing and its Ledger path), `MultisigConfigModel`, the chain models | 2 files, +153 / −2 (137 code): reads the file into Neuron's models, writes back the signatures Neuron adds; fixes `signMultisig` so witnesses beyond the inputs are signed | The 10 relevant test files: 103 passed, 24 failed before and after (the failures need a SQLite module the install didn't build) |

**Creating the file** ([XRT-4](experiments/XRT/results.md#xrt-4-creating-the-file-inside-the-wallets)): ckb-cli `tx sigsheet-new`, +91 lines (87 code), with its own tests 7 of 7; CCC, a 59-line module (52 code); CCC writes byte-identical bytes for ckb-cli's transaction; both flows committed. Neuron's creation step wasn't measured: its export already fetches the input transactions ([background §5](background.md#5-neuron-v02041)), so its patch would convert that export.

**Not measured:** user-interface work (Neuron's renderer and IPC; CCC has none; ckb-cli's interface is the subcommands).

**What each wallet must fix whatever the format** ([X1](experiments/X1/results.md#interoperability-findings)): Neuron must hash witnesses beyond the inputs (the patch does, and its signature then commits, [X5](experiments/X5/results.md) F4); ckb-cli and Neuron can't sign the 2024 deployment, and the patches keep that as it is: ckb-cli passes such a file on unchanged ([X5](experiments/X5/results.md) F7).

**The maintainers' public statements** (none of them has been asked, and none has commented on this design):
- **ckb-cli.** The requests and reports in section 1.1 ([#603](https://github.com/nervosnetwork/ckb-cli/issues/603), [#584](https://github.com/nervosnetwork/ckb-cli/issues/584), [#569](https://github.com/nervosnetwork/ckb-cli/issues/569)). PR #652 (merged 2025-12-01) makes ckb-cli "detect multisig type (Legacy/V2) from actual input cell locks instead of deployment config", the same rule this design uses ([PR #652](https://github.com/nervosnetwork/ckb-cli/pull/652)); on PR #651, a maintainer wrote "we can deduce the `code_hash` from the transaction" ([PR #651](https://github.com/nervosnetwork/ckb-cli/pull/651#issuecomment-3578784837)).
- **Neuron.** A maintainer pointed the format mismatch to the one-way ckb-cli import: "Should be resolved by" neuron#3169 ([neuron#3048](https://github.com/nervosnetwork/neuron/issues/3048#issuecomment-2154110104)). On PR #3347: "Fallback to a value is kind of dangerous when it's about ownership." ([PR #3347](https://github.com/nervosnetwork/neuron/pull/3347#discussion_r2067770925)), which matches the design's rule of reading the deployment from the input cell instead of a declared field. Neuron's request to "Support managing Nervos DAO assets with multisig addresses" was closed as completed on 2025-03-05 ([neuron-public-issues#425](https://github.com/Magickbase/neuron-public-issues/issues/425)). A maintainer traced a Ledger failure to an input-transaction context "too large" for the app's buffer ([neuron#3095](https://github.com/nervosnetwork/neuron/issues/3095#issuecomment-2452146987)).
- **CCC.** CCC's maintainer built its multisig signers and their aggregation ([background §6](background.md#6-ccc-ckb-ccccore-1231)), wrote about a P2P network for multisig wallets ([t/10794/5](https://talk.nervos.org/t/10794/5)), and reintroduced CoBuild in CCC only for the Coin package ([t/10597/1](https://talk.nervos.org/t/10597/1)).
- **So:** the record shows each project's maintainers working on the pieces this design uses (deriving the deployment from inputs, aggregating signatures, carrying input transactions) and a core developer asking for request files. No maintainer has said anything about a shared format; whether they would adopt one is **open**.

## 8. Phase 1: Sigsheet v0.1, scope and acceptance tests

Phase 1 is complete and usable on its own. The measured sizes above come from throwaway patches; phase 1's work is a spec and implementations written for review.

### 8.1 Deliverables

| # | Deliverable | What it contains | Design-stage basis |
|---|---|---|---|
| P1 | **The specification, v0.1** | The file (section 3.1, with the inclusion proofs), the reader's checks, the message rule of each lock kind it signs (single-key, the three multisig deployments), merge and finalize (with the genesis rule and partial finalize), what a signer is shown, creation, the extension rule; an informative annex for the CoBuild profile; the CKB IDL boundary | Sections 3 and 5 |
| P2 | **Test vectors** | The 12 cases of X2 (PR #34 and the genesis 2-of-3 payment from mainnet; ten devnet cases); a DAO withdrawal of two deposits with its proofs; a lock the reader doesn't sign; an Omnilock-mode group; the genesis positions; creation; and each attack file of X4, XRT and XRTb, each with its expected bytes, messages, merge result and final transaction | X2, X3, X4, XRT, XRTb |
| P3 | **Two independent implementations** | A TypeScript library on CCC, the reference implementation; and the ckb-cli commands, in Rust: create, check, show, sign through the tool's own signer, merge, finalize and send | CCC 229 + 52 code lines; ckb-cli 381 + 87 (X6, XRT-4) |
| P4 | **Neuron** | Reading a file into Neuron's models, signing through its own `signMultisig` (and so its Ledger path), writing it back, creating it from Neuron's export, and the fix so witnesses beyond the inputs are signed | 137 code lines (X6); its user interface and creation step aren't measured |
| P5 | **The changes offered upstream** | P3 and P4 as pull requests to ckb-cli, CCC and Neuron, each with its tests; merging them is each project's decision, not a phase 1 deliverable | Each wallet's own tests unchanged (X6, XRT-4) |
| P6 | **A testnet demo** | A 2-of-3 genesis and a 3-of-5 v2 multisig, each signed in at least two of the three tools on one shared file, once passed along and once posted and merged by someone who isn't a signer; a multisig input next to a single-key input (PR #34's shape); every transaction hash published. The demo runs on testnet only; the tools also have a mainnet setting, so that users can use them on mainnet | X5's seven devnet flows |
| P7 | **A community feedback round** | The spec draft posted on Nervos Talk; every comment answered in public, and the changes listed | - |

### 8.2 Acceptance tests

Each is checkable without reading the code. They are phase 1's definition of done.

1. **Vectors:** both implementations (P3) reproduce every P2 vector byte for byte: the file, the unsigned id, every group's message, the merged file and the final transaction.
2. **Attacks:** both refuse each X4 attack file or drop its signatures, and still finalize the honest file.
3. **Merge:** for each vector, the merge of its partial files in at least 200 random orders and groupings gives one byte string.
4. **Offline:** with networking off, every check in the spec runs except creation and sending.
5. **Cross-tool:** a file created by each tool is read and signed by the other two, for every case the tools support (ckb-cli and Neuron don't sign the 2024 deployment today).
6. **Genesis:** for a genesis multisig with N ≥ 11, the finalizer's choice passes a node's `test_tx_pool_accept`.
7. **Each wallet's own tests** pass before and after its change.
8. **Testnet:** the P6 transactions are on testnet, with their hashes and the tool behind each signature.
9. **Feedback:** the P7 post, its replies, and the list of changes.
10. **Nervos DAO:** on the two-deposit vector, both implementations show the node's fee (0.001 CKB) from the proofs, show an upper bound without them, and refuse a proof whose block hash was changed.

Test 10 is the one that lets the claim "a signer sees the real fee of a Nervos DAO withdrawal" be made firmly. Until it passes on the phase 1 implementations, that claim rests on the prototypes only ([XRTb-3](experiments/XRTb/results.md#xrtb-3-a-nervos-dao-withdrawal-of-two-deposits)).

## 9. Later versions

### v0.2: more locks and more ways to move a file (only broadens v0.1)

- **Omnilock's multisig mode** as a lock kind, through the extension rule (D18): no new field and no version change; v0.1 readers carry its groups.
- **An optional relay transport** for signatures: a signer posts one signature with the ids that place it (367 bytes, [X7](experiments/X7/results.md#1-sizes-bytes)), or a whole file where it fits; files still work without it.
- **A readable summary for signers**, derived only from checked data (the "markdown guidance for signers" of [ckb-cli#603](https://github.com/nervosnetwork/ckb-cli/issues/603)).
- **The genesis binary's rejected positions measured beyond N = 24**, so the finalize rule needs no node check for larger multisigs.
- **Known token scripts beyond xUDT and sUDT** decoded as they ship.
- **More tools** reading and writing the file.

### v1.0: a stable standard (only broadens v0.2)

- **The specification proposed as a CKB RFC** (nervosnetwork/rfcs), with the feedback rounds' changes.
- **New lock kinds as they ship:** the "arbitrary multisig" script (RFC number 56 reserved) and locks that sign CKB_TX_MESSAGE_ALL (RFC number 55 reserved) ([background §9](background.md#9-omnilocks-multisig-mode-and-future-locks)), each taking its signing description from CKB IDL where CKB IDL defines one.
- **A conformance suite** that any implementation can run, with independent implementations listed.
- **The CoBuild profile kept in step** with CoBuild as it moves from deferred to shipped.

## 10. Counter-evidence: the strongest case that the design is wrong

1. **Adoption may not come.** G1 in practice needs the three projects to ship the change, and no maintainer has said anything about a shared format (section 7). Until then the file is a format for patched tools.
2. **G2 is met narrowly.** No one person collects and forwards, but each signer still receives the file and sends a copy on; the coordinating is reduced, not removed. A relay would automate delivery, and CKB's DevRel lead has floated a P2P network for multisig wallets ([t/10794/5](https://talk.nervos.org/t/10794/5)); that is a later version here.
3. **The slow part may not be gathering.** PR #34 reached its threshold in under two hours and took about six days more to reach the chain (section 1.1); if the wait is review or scheduling, Sigsheet won't shorten it.
4. **Overlap with CoBuild.** CoBuild's building packet was designed for this exchange role ([t/7702/1](https://talk.nervos.org/t/7702/1)). The answer is a measured lossless mapping and the reasons in section 6.1, but a reviewer could still see a second container.
5. **The hardware path is narrow today.** Ledger's Nervos app 0.6.3 signs only genesis multisig transactions without blind signing (section 5.7); funds under v2 and 2024 can't be checked on that device, with or without Sigsheet.
6. **The genesis binary rejects some valid signature sets** (section 5.5): for large genesis multisigs, finalizing needs a rule that skips positions and a node check.
7. **Size:** hex JSON doubles the bytes; PR #34's file is 733 KB, above every relay limit seen.

## 11. Risks and open items

| # | Risk or open item | Status | What would settle it |
|---|---|---|---|
| 1 | **The three projects may not adopt it.** G1 in practice needs ckb-cli, Neuron and CCC to ship the change | Open; public evidence only (section 7) | Phase 1 offers the changes upstream with tests (P5) and runs a public feedback round (P7) |
| 2 | **G2 is met narrowly:** each signer still receives the file and sends a copy on | Measured ([X5](experiments/X5/results.md)) | A relay transport in v0.2; the file works without it |
| 3 | **A reviewer may see a second container next to CoBuild's building packet** | Answered by a measured mapping (section 6.1) | The spec states the mapping; the feedback round tests the reading |
| 4 | **Ledger's Nervos app 0.6.3** refuses v2 and 2024 multisig transactions at any size unless "Allow sign hash" is on, which signs blind; a multisig input next to another input; and more than five outputs | The app's limits, not Sigsheet's, and not a matter of size (section 5.7) | A newer app; nothing in the format blocks it |
| 5 | **A real Ledger's transfer time and watchdog** on a long stream | Open: no device run | A device run with a test seed; the same under every format |
| 6 | **The genesis binary's rejected positions beyond N = 24** | Open | The XRT-1 sweep extended to N = 255 (v0.2); until then the finalizer checks large genesis multisigs with a node |
| 7 | **Neuron's creation step and every wallet's user interface** | Unmeasured | Phase 1 (P4) |
| 8 | **CKB IDL's deferred "partial-signing metadata"**, and reuse in TypeScript | Open: undefined in CKB IDL's sources; no TypeScript client yet | The design rule keeps Sigsheet from pre-empting it (section 6.2) |
| 9 | **Omnilock's multisig mode through v0.1 readers** | The rule is decided and tested with a stand-in lock ([XRT-3](experiments/XRT/results.md#xrt-3-a-lock-the-reader-doesnt-sign)); an Omnilock run itself is open | v0.2 adds the lock kind; v0.1 readers already carry groups they don't sign |
| 10 | **A config listing one key twice** is refused, though the lock accepts it (and then one key controls two slots) | A stated limit ([XRT-1](experiments/XRT/results.md#xrt-1-which-valid-signature-sets-each-deployed-binary-accepts)) | None needed: ckb-sdk refuses such configs too, and no source shows one on chain |
| 11 | **Hex JSON doubles the bytes;** PR #34's file is 733 KB | Measured ([X2](experiments/X2/results.md#2-bytes-zlib-level-9-in-brackets), [X7](experiments/X7/results.md)) | A binary view (the CoBuild profile) where size matters |
| 12 | **During adoption, unpatched tools can't read the file** | Measured ([X1](experiments/X1/results.md): today's formats don't interoperate either) | Each tool's change is small (X6, XRT-4) |
| 13 | **A Nervos DAO withdrawal file without inclusion proofs** shows the fee as an upper bound ("at most") | Measured ([XRTb-3](experiments/XRTb/results.md#xrtb-3-a-nervos-dao-withdrawal-of-two-deposits)) | Creation adds the proofs; a reader never lowers the fee on an unproven block hash |
| 14 | **A conflicting copy for a group a reader doesn't sign blocks that reader's merge** | By design: refusing keeps the valid signature ([XRTb-2](experiments/XRTb/results.md#xrtb-2-the-simpler-rules-against-the-design-rules-offline)) | A reader that signs the kind resolves it by verifying |
| 15 | **Tokens other than xUDT and sUDT** (Spore and others) aren't decoded | Shown as type scripts and data hashes, with the "leaves" warning | Known scripts added as they ship (v0.2) |
| 16 | **The design-stage numbers** come from throwaway prototypes and patched copies of the wallets | By design | Phase 1's acceptance tests re-measure them on the real implementations |
