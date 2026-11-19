# Sigsheet: the design record and benchmarks

**Run the benchmarks yourself:**

```sh
./bench/run.sh
```

Python 3 (tested with 3.14.4), standard library only, offline: about 4 minutes, or 7 with the mainnet inputs, on a 2-CPU machine. It re-runs every design-stage benchmark that works on a plain machine and prints each measured value next to the recorded one: PASS or FAIL for deterministic values (counts, bytes, byte-identical round trips), and times labelled as your machine's, for reference only. Details, the optional mainnet fetch and the steps that need a devnet or the wallets: [bench/README.md](bench/README.md).

---

This is the `research` branch of Sigsheet. It holds the design record and the benchmarks behind Sigsheet: the problem the format solves, every design decision with its evidence, the paths considered and why each was dropped, and the experiments that measured them. **It is never merged into `main`:** its history is separate, and the code that implements Sigsheet lives on `main`.

Sigsheet is an open format, with rules, for a CKB transaction that several people sign. ckb-cli, Neuron, CCC and other tools all read the same file and add their signatures to it directly, so signatures work across tools with no bridge in the middle and no one has to collect and forward them.

**Every number here is design-stage:** measured on throwaway prototypes and on patched copies of the wallets, on a local devnet with fresh test keys. Phase 1 builds the real implementations and re-measures the design through its acceptance tests; those numbers will be added here next to these, clearly labelled.

## What's here

| File | What it is |
|---|---|
| [design-record.md](design-record.md) | The design record: the problem, the decisions and their evidence, how the design is checked, the security analysis (attacks and objections considered, and how the design answers them), phase 1's scope and acceptance tests, and the later versions |
| [paths.md](paths.md) | The seven paths considered, and why each was dropped or kept |
| [scoreboard.md](scoreboard.md) | How the paths that pass every gate score, criterion by criterion |
| [numbers.md](numbers.md) | Every measured number, with its conditions and its source |
| [background.md](background.md) | The facts the design rests on (CKB's multisig lock, today's wallets, CoBuild, CKB IDL, other ecosystems), each with its source |
| [sources.md](sources.md) | Every upstream repository and the commit each citation is pinned to |
| [experiments/](experiments/README.md) | The experiments, each with its README (question, method, exact commands) and its results; the prototypes; the wallet patches as diffs |
| [bench/](bench/README.md) | The benchmark runner |
| [LICENSE](LICENSE) | The MIT license of this branch's own content, the same as `main`'s |

## The design in one paragraph

One canonical JSON file per transaction ([design record §3](design-record.md#3-the-design-decisions-with-their-evidence)) carries the transaction with its witness templates, the previous transaction of every input (so a signer checks every input cell offline, by hash), the block headers and inclusion proofs a Nervos DAO withdrawal needs, the multisig configs (checked against the lock args), and every signature so far, keyed by lock group and signer. Signers pass the file along, or post copies that anyone merges in any order into the same bytes; whoever holds a ready file finalizes it. It works with the three existing multisig deployments and the addresses that already exist, maps losslessly onto CoBuild's building packet, and leaves signing rules to the locks and to CKB IDL.

## The key numbers (design-stage)

| Measure | Value | Source |
|---|---|---|
| ckb-cli, CCC and Neuron signing one shared file with no collector | 7 devnet flows, all committed | [X5](experiments/X5/results.md) |
| Code each wallet needed: ckb-cli, CCC, Neuron | 381, 229, 137 code lines; each wallet's own tests unchanged | [X6](experiments/X6/results.md) |
| Merge orders giving identical bytes | 3,150 of 3,150 trials | [X3](experiments/X3/results.md) |
| Attacks caught | every one tested, in every format | [X4](experiments/X4/results.md) |
| File size: the genesis 2-of-3 payment, PR #34 | 2,371 bytes, 733,078 bytes | [X2](experiments/X2/results.md) |
| The fee of a Nervos DAO withdrawal of two deposits, from inclusion proofs | exactly the node's (0.001 CKB) | [XRTb-3](experiments/XRTb/results.md#xrtb-3-a-nervos-dao-withdrawal-of-two-deposits) |

## License

This branch's own content (the design record, the scripts and the data written for this research) is under the MIT license in [LICENSE](LICENSE), the same license as `main`. Code from other projects appears only inside diffs against their pinned commits; each diff's upstream parts (its context and removed lines) are under that project's license, which the `NOTICE.md` next to the diff names and gives in full, with its copyright notice ([sources.md](sources.md#licenses-of-third-party-code)).
