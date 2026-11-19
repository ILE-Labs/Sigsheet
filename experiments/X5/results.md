# X5 results: one shared file, three wallets, no collector, on the devnet

Conditions (design-stage): 2026-11-18 (UTC); local devnet (ckb 0.210.0); the X6 patches of ckb-cli v2.0.0, CCC 1.23.1 and Neuron v0.204.1, each signing with its own code; fresh test keys. Every step's file and its SHA-256: `results/`. Commands: `README.md`.

## 1. Seven flows, seven committed transactions

| Flow | What it shows | Transaction | Block |
|---|---|---|---|
| F1 | 2-of-3 v2, one file passed along: ckb-cli signs, then CCC signs the file it received and finalizes | `0xe59840d59f37a707904b4b39f098960ca9dc2411915a835c0d49fbee03588a8a` | 17,310 |
| F2 | 3-of-5 v2, four signers in four tools on their own copies; three different tools merge the copies in three orders and get **the same bytes**; ckb-cli finalizes with 3 of the 4 (members 0, 2, 3) | `0x0f44c2b254d3cb01abd9189820db0ae8efc202d7c7b11fa2482c87e692a928d2` | 17,335 |
| F3 | 2-of-3 genesis: Neuron signs first, ckb-cli second and finalizes | `0x5f7c2bd61d81fa45d11cdd45497cf317b2fe2fc0eb063171b3aff771919db483` | 17,348 |
| F4 | a witness beyond the inputs (X1's S9 shape): Neuron (patched) and CCC; both signatures valid | `0xf8fb2235c5a9ad0bf767cc60519e31967c4c5994842a6d66191e5dcd5b0b79af` | 17,366 |
| F5 | PR #34's shape, a multisig input next to a single-key input: ckb-cli signs the single-key input, CCC and Neuron sign the multisig, each on its own copy; Python merges; CCC finalizes | `0x66c2a43afe5df63dbe44cf75db99ae32db615eb24caefa9c7cb2b6efffc1a9a1` | 17,384 |
| F6 | 3-of-5, R = 1: three non-required members sign; ckb-cli's finalize **refuses** ("isn't ready"); the required member signs with ckb-cli; then it finalizes | `0x2c2b590166d81b65cb376b37a95923f7fd92aca02b9df5cd406071e4642421c8` | 17,400 |
| F7 | the 2024 deployment: CCC signs; ckb-cli can't sign this lock, **adds nothing and passes the file on unchanged** (`signatures_added: 0`); CCC adds a second signature and finalizes | `0x9963afdf2e8305541e2fcafc034d94de7ff97e8881ef93df8931b71c24d196ae` | 17,410 |

Every final transaction also passes the lock's rules in Python before it is sent (`lock_rules_python: true`).

## 2. What else the runs show

- **No bridge in the middle (G1):** every signer read the file another tool wrote and added its signature to it directly. The files are canonical: ckb-cli's file after signing with s1 is byte-identical to CCC's after signing with s1 (deterministic signatures, the same canonical JSON; X6 `scratch/`), and the strict Python reader accepts every file each tool wrote.
- **No collector (G2):** F1, F3, F4 and F7 pass one file from signer to signer, and the last signer finalizes; F2, F5 and F6 let each signer post a copy, and anyone, a signer or not, merges them in any order. No step needs one person to collect and forward.
- **The tool limits pass through:** a tool that can't sign a lock (ckb-cli with the 2024 deployment) leaves the file as it is, and the next tool carries on (F7).
- **Timing on this server:** a ckb-cli signature took 0.04-0.13 s; CCC about 2 s and Neuron about 9-12 s per step, almost all of it starting Node, tsx or jest (the CCC module's own time was 122-229 ms per signature; `results/x5-*.json`).

## Answer

G1 and G2 hold end to end on the devnet: ckb-cli, CCC and Neuron, each with its own signing code, read and sign one shared Sigsheet file in any order, passed along or posted and merged by anyone, and the chain accepts all seven resulting transactions, for 2-of-3 and 3-of-5, genesis, 2024 and v2 locks, R = 1, a mixed multisig and single-key transaction, and a witness beyond the inputs.
