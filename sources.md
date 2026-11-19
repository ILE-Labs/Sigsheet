# Sources and pinned commits

Every code citation in this branch is a permalink at one of these commits. To reproduce an experiment that reads upstream code, clone the repository and check out the commit; the experiments' READMEs say which ones they need. The scripts expect such clones under `refs/` at the repository root (`refs/<folder>`), which git ignores.

## CKB code and specs

| Folder under `refs/` | Repository | Commit | What it is |
|---|---|---|---|
| `ckb-system-scripts` | <https://github.com/nervosnetwork/ckb-system-scripts> | `72eb92fca090700dcb398cd8cad8fbd8bad40355` (tag v0.6.0, 2025-05-13) | The multisig lock source; the 2024 fix is `934166406fafb33e299f5688a904cadb99b7d518` (#98); v2 is PR #99 |
| `nervos-secp256k1` | <https://github.com/nervosnetwork/secp256k1> | `3ffde18a060aaf4df5b81e7d88355f1e99874650` (2019-07-30) | The secp256k1 that ckb-system-scripts pins as `deps/secp256k1` |
| `rfcs` | <https://github.com/nervosnetwork/rfcs> | `0c945451c24194f4d34d81195c0159df0a67581a` (2026-10-26) | CKB RFCs |
| `ckb` | <https://github.com/nervosnetwork/ckb> | `2592ddf0502cd4adfe886db893cccc866db3c60f` (tag v0.210.0, 2026-09-17) | The node: consensus limits, `ckb.toml`, the RPC README |
| `ckb-cli` | <https://github.com/nervosnetwork/ckb-cli> | `80efc21c30e9fc7847407a217034681b6e46c763` (tag v2.0.0, 2025-12-03) | The same version as the `ckb-cli 2.0.0 (80efc21 2025-12-03)` binary the experiments ran |
| `ckb-sdk-rust` | <https://github.com/nervosnetwork/ckb-sdk-rust> | `3a418e7048c8864c15548e838072495edefbc24f` (tag v5.0.0, 2025-10-31) | ckb-cli v2.0.0 depends on `ckb-sdk` 5.0.0 from crates.io |
| `neuron` | <https://github.com/nervosnetwork/neuron> | `d3a7467d218e4b6f777326682a83fec802669c00` (tag v0.204.1, 2026-04-10) | The latest Neuron release at the time |
| `ccc` | <https://github.com/ckb-devrel/ccc> | `7095ccad564b94ea2e59284cb4a364aa3499252e` (tag `@ckb-ccc/core@1.23.1`, 2026-11-17) | `@ckb-ccc/core` 1.23.1, npm's `latest` at the time |
| `ccc-next-major` | <https://github.com/ckb-devrel/ccc> | `8cdbf527921fe84ecc2cab5ad511d21ef5960e34` (branch next-major, 2026-11-17) | CCC 2.0 prerelease, with `packages/co-build` |
| `omnilock` | <https://github.com/nervosnetwork/omnilock> | `280dd97ac0930ea1ed766a18d49478229347c832` (2026-09-07) | Omnilock, for its multisig mode |
| `docs.nervos.org` | <https://github.com/nervosnetwork/docs.nervos.org> | `6a6152f4e424353032eac41864350b948efad913` (2026-11-16) | Official docs, including the public RPC list |
| `nostr-binding` | <https://github.com/nervosnetwork/nostr-binding> | `eef134e0a09dd07ccc367eb4eca84c1a5a73fb8b` (2026-01-14) | A mainnet multisig deployment record |
| - | <https://github.com/nervosnetwork/fiber-scripts> | `026027f54f6a90cb48d8cc184b230e2018bb8611` | `deployment/mainnet/mainnet.json`, the PR #34 deploy file (SHA-256 `8563ba8dcd0d051822dd0cc21db995dc8e6a2984e900d3500068f0185a07b51e`) |

## CoBuild, prior art and CKB IDL

| Folder under `refs/` | Repository | Commit |
|---|---|---|
| `ckb-transaction-cobuild-poc` | <https://github.com/cryptape/ckb-transaction-cobuild-poc> | `e29514f9b1206b40f2bbc7b97e86c6f35373b0b0` (2024-01-30) |
| `ckb-multisig-cobuild-poc` | <https://github.com/cryptape/ckb-multisig-cobuild-poc> | `84bdc99ad5e62f8e7a90a30e4d8bcdc1a53b468a` (2024-03-05) |
| `ckb-idl/ckb-idl-spec` | <https://github.com/ckb-idl/ckb-idl-spec> | `ebec1696b3df3336262c479650611bb344489f01` (2026-09-28) |
| `ckb-idl/ckb-idl-cli` | <https://github.com/ckb-idl/ckb-idl-cli> | `c5fb2d728f1e6e09321401d85f03e7213272d1a8` (2026-09-29) |
| `ckb-idl/ckb-idl-client` | <https://github.com/ckb-idl/ckb-idl-client> | `e7d8124921dc640018004a4a031fc6146535e334` (2026-09-29); also `beacadd45e7753d0c2fd210a12322380716ea9d5` (`master`, 2026-09-25) |
| `ckb-idl/ckb-idl-derive` | <https://github.com/ckb-idl/ckb-idl-derive> | `7d9658cd155a98d56f7066f3cfc4dcf5f7e2e60b` (2026-09-29) |
| `ckb-idl/script-registry` | <https://github.com/ckb-idl/script-registry> | `b37ef146f897d1b78a633bd16df0536a5a978ad6` (2026-11-13) |

## Hardware wallets

| Folder under `refs/` | Repository | Commit |
|---|---|---|
| `app-nervos` | <https://github.com/LedgerHQ/app-nervos> | `8c50034c8109f90d87c2b3c413361ef83f5b2e03` (2026-08-21; app version 0.6.3) |
| `_ledger/ledger-secure-sdk` | <https://github.com/LedgerHQ/ledger-secure-sdk> | `473fe57b98c24ce9488b1dfecd51ad92fe665d19` (tag v26.6.1) |
| `hw-app-ckb` | <https://github.com/magickbase/hw-app-ckb> | `78fd71b48b4f33881e4f3c3170eb1ef780c69713` (version 0.2.0-alpha.0) |
| `speculos` | <https://github.com/LedgerHQ/speculos> | `82fbd97a91ffcf1fbf9eb0201a95b70c09dfe921` (tag v0.27.6) |

## Other ecosystems

| Repository | Commit |
|---|---|
| <https://github.com/bitcoin/bips> | `a7f91321f25b5be8d93e901775621c21519e80b7` (2026-11-17) |
| <https://github.com/ElementsProject/elements> (`doc`) | `3c40bb994720616841715448cb9957ada984c556` (2026-10-21) |
| <https://github.com/kaspanet/rusty-kaspa> (`wallet/pskt`) | `338d13c13826531ccbf9b29df4c2bdaeef895900` (2026-11-15) |
| <https://github.com/zcash/librustzcash> (`pczt`) | `33644a5da0017de271ab0f057aeefdbce6684461` (2026-11-16) |
| <https://github.com/nostr-protocol/nips> | `bec0fc89e75645e77a06d145598246efca844457` (2026-11-16) |

## Chain data

- **Mainnet:** read-only JSON-RPC calls to `https://mainnet.ckb.dev/`, the public endpoint listed in [docs.nervos.org's RPC page](https://github.com/nervosnetwork/docs.nervos.org/blob/6a6152f4e424353032eac41864350b948efad913/website/docs/getting-started/rpcs.mdx). Which mainnet transactions the experiments use, and how to fetch them: [experiments/mainnet-inputs.md](experiments/mainnet-inputs.md).
- **Devnet:** a local chain made with `ckb init --chain dev` ([X1](experiments/X1/README.md)). Nothing was sent to testnet or mainnet.

## Licenses of third-party code

Upstream code appears here only inside diffs against the commits above. Each project's license is named, and given in full with its copyright notice, in the `NOTICE.md` next to the diff: see the `NOTICE.md` files in [X1/rust](experiments/X1/rust/NOTICE.md), [X1/neuron](experiments/X1/neuron/NOTICE.md), [X6/ckb-cli](experiments/X6/ckb-cli/NOTICE.md), [X6/ccc](experiments/X6/ccc/NOTICE.md), [X6/neuron](experiments/X6/neuron/NOTICE.md), [X6/neuron/harness](experiments/X6/neuron/harness/NOTICE.md), [X6/ckb-cli-idl](experiments/X6/ckb-cli-idl/NOTICE.md), [XRT](experiments/XRT/NOTICE.md) and [XQ14](experiments/XQ14/NOTICE.md).
