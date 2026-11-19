# XQ14 results: a Ledger signing Sigsheet multisig transactions, on Ledger's emulator

Conditions (design-stage): 2026-11-18 (UTC). The Ledger Nervos app 0.6.3 (`app-nervos` `8c50034`), built here for the Nano S Plus with SDK v26.6.1, run in Speculos 0.27.6 with the emulator's default test seed ([`speculos/main.py` L60-L62](https://github.com/LedgerHQ/speculos/blob/82fbd97a91ffcf1fbf9eb0201a95b70c09dfe921/speculos/main.py#L60-L62)); no device and no real keys. Host side: `@magickbase/hw-app-ckb` 0.2.0-alpha.0, the version Neuron pins ([package.json L52](https://github.com/nervosnetwork/neuron/blob/d3a7467d218e4b6f777326682a83fec802669c00/packages/neuron-wallet/package.json#L52)), through `@ledgerhq/hw-transport-node-speculos` 6.34.7. The device's key: m/44'/309'/0'/0/0, lock args `0xe5260d83…863d` (`results/pubkey-path0.json`). Transactions finished and committed on the local devnet only. Every run's files, device record (each screen's text, every button press) and outcome are in `results/runs/<run>/`; the emulator's logs in `results/speculos/`.

## 1. What happened, run by run

| Run (`results/runs/…`) | What it tests | Device | Screens (presses) | Outcome |
|---|---|---|---|---|
| `genesis-member` | 2-of-3 genesis [device, s1, s2]; a payment and change back to the multisig | **signed** | 11 (10 right, 1 both) | Signature recovers to the device key over the lock's message; with s1's, committed on devnet: `0xa6d8a1ec…7dcd`, block 15,689 |
| `two-inputs-one-group` | two cells of that multisig in one transaction | **signed** | 7 (6, 1) | Committed: `0x7f91b994…f928`, block 15,758 |
| `dao-payout-replay` | the real genesis 2-of-3 payment (mainnet data; device not a member; nothing sent) | signed | 11 (10, 1) | Shows the payment; a non-member signature, of no use |
| `genesis-nonmember` | 2-of-3 genesis whose members don't include the device | **signed** | 7 (6, 1) | The device signs for a multisig it isn't in: no membership check |
| `v2-member` | the same members under v2 (`data1`) | **app exits** | 0 | "exit called (255)"; the host sees a disconnect, not an error code |
| `2024-member` | the same members under the 2024 deployment | **app exits** | 0 | as v2 |
| `v2-member-contract-data` | v2, with the user setting "Allow contract data" on | signed | 8 (7, 1) | Shows a normal transfer with "Contract: Not Present", but **the signature is over the wrong message** (recovers to `0x5d7eeed5…`, not the device key): useless on chain |
| `v2-blind-hash` | v2, with the user setting "Allow sign hash" on: the lock's message sent to `INS_SIGN_MESSAGE_HASH` | **signed** | 5 (4, 1): "Sign Message Hash" and 32 bytes of hex | Valid; committed: `0x25747c22…3720`, block 15,806. **Signed blind**: no amount, fee or destination shown |
| `multisig-plus-single-key` | the multisig input next to a single-key input | app exits | 0 | The app's rule: no multi-input transaction with a multisig input |
| `six-outputs` | six payments and change | app exits | 0 | The app's limit: five non-change outputs |
| `pr34-replay-default`, `pr34-replay-contract-data` | the real PR #34 transaction (v2 multisig, a single-key input, code cells with data and type IDs; 649,900 bytes to the device) | app exits | 0 | Refused with both settings |

Why each refusal happens is in the app's code: it knows only the genesis multisig and the single-key lock ([`src/apdu_sign.c` L336-L358](https://github.com/LedgerHQ/app-nervos/blob/8c50034c8109f90d87c2b3c413361ef83f5b2e03/src/apdu_sign.c#L336-L358)); it refuses a multi-input transaction with a multisig input ([L667-L669](https://github.com/LedgerHQ/app-nervos/blob/8c50034c8109f90d87c2b3c413361ef83f5b2e03/src/apdu_sign.c#L667-L669)) and more than five outputs ([`MAX_OUTPUTS`](https://github.com/LedgerHQ/app-nervos/blob/8c50034c8109f90d87c2b3c413361ef83f5b2e03/src/apdu_sign.c#L576)). In 0.6.3 a refusal makes the app quit instead of returning 0x6985: its main loop no longer catches thrown errors ([`src/apdu.c` L109-L154](https://github.com/LedgerHQ/app-nervos/blob/8c50034c8109f90d87c2b3c413361ef83f5b2e03/src/apdu.c#L109-L154), after the 0.6.2 move to the SDK's standard app).

## 2. Size is not the limit in 0.6.3

`results/size-probes.json`: synthetic previous transactions of growing size, spent once or twice (twice is PR #34's shape: hw-app-ckb sends input i's previous transaction as context i, so a shared one goes twice, [Ckb.js L243](https://github.com/magickbase/hw-app-ckb/blob/78fd71b48b4f33881e4f3c3170eb1ef780c69713/src/Ckb.js#L243)).

| Previous transaction (raw bytes) | Sent to the device, spent once | Spent twice |
|---:|---|---|
| 460 | 1,012 bytes, 5 APDUs: signed | 1,540 bytes, 7 APDUs: signed |
| 64,460 | 65,012 bytes, 283 APDUs: signed | 129,540 bytes, 564 APDUs: signed |
| 283,460 (PR #34's is 284,008) | 284,012 bytes, 1,235 APDUs: signed | 567,540 bytes, 2,468 APDUs: signed |
| 1,000,460 | 1,001,012 bytes, 4,353 APDUs: signed | 2,001,540 bytes, 8,703 APDUs: signed |

Every signature verifies. The app streams the transaction through a parser and hashes as it goes, with no total-size limit in that path. So the 0x9405 in [neuron#3095](https://github.com/nervosnetwork/neuron/issues/3095) (app 0.6.0 on a Nano S and a Nano X) isn't reproduced by 0.6.3 here; whether it came from 0.6.0 or the older devices can't be tested in this Speculos, which no longer runs the Nano S or 0.6.0's API level (it ships shared libraries for API levels 22 and 24-27 only).

## 3. The three formats give the device the same bytes

For every run, the device job built from the C file, the B+w file and the A file is identical (`same_device_job_from_C_Bw_A: true` in every `result.json`). The device job is what Neuron's `signMultisig` passes today (raw transaction, the group's witnesses with the zeroed multisig lock, the previous transactions as `context`, the sign path, Neuron's account path as the change path; `scripts/job.py`). One deliberate difference from Neuron: witnesses beyond the inputs are included, since the lock's message covers them (X1, S9).

## 4. The emulator, friction and security

**The emulator against a real device.** The emulator runs the app's own code (built from the release's source and SDK; not Ledger's signed binary, which this build doesn't reproduce byte for byte) on an emulated CPU, so the app's logic, its fixed buffers and its screens are the device's. Speculos itself says "There is absolutely no guarantee that apps will have the same behavior on hardware devices and Speculos, though the differences are limited", and lists what it doesn't emulate: some syscalls, the Nano S Plus's alignment faults, stack overflows between syscalls, and the watchdog of the Nano X, Flex, Apex and Stax ([README L71-L140](https://github.com/LedgerHQ/speculos/blob/82fbd97a91ffcf1fbf9eb0201a95b70c09dfe921/README.md#L71-L140)). Not tested here, so open until a device run: how long a real device takes to receive 2,826 APDUs (PR #34's size) over USB, and whether the watchdog interrupts very long streams; physical button handling.

**User friction** (the same under C, B and A, since the device receives the same bytes; and the same as today's Neuron path):
- A 2-of-3 payment with change back to the multisig: 11 screens, 10 right presses and one press of both buttons. The change back to the multisig is shown as a second payment to a multisig address, and the "Amount" screen counts it: 999 CKB for a 500 CKB payment, and 8,559,214 CKB for the genesis 2-of-3 payment's 2,873,564 CKB. The signer must read both addresses to tell the payment from the change.
- Refused transactions (v2 or 2024 locks, a multisig input next to another input, six or more outputs) make the app quit without an error code, so the wallet can only say the device disconnected.
- Size didn't matter on the emulator up to 2 MB.

**Security:**
- **Checked by the device before signing:** every input's previous transaction (hashed on the device, so input amounts and the fee can't be falsified, [apdu_sign.c L316](https://github.com/LedgerHQ/app-nervos/blob/8c50034c8109f90d87c2b3c413361ef83f5b2e03/src/apdu_sign.c#L316)); every output's amount and address; the fee. No output to a multisig is ever hidden as change.
- **Not checked:** that the device's key is a member of the multisig (`genesis-nonmember`); R, M and the member list; which deployment (except that it knows only genesis). A non-member signature is useless on chain, and Neuron checks membership on the host ([transaction-sender.ts L323](https://github.com/nervosnetwork/neuron/blob/d3a7467d218e4b6f777326682a83fec802669c00/packages/neuron-wallet/src/services/hardware/transaction-sender.ts#L323)).
- **Signed blind:** only through the "Allow sign hash" setting (off by default, `src/main.c` L24), which signs any 32-byte value after showing it as hex (`v2-blind-hash`). With that setting on, a compromised host could get any transaction's lock message signed. The "Allow contract data" setting makes the v2 and 2024 locks signable but with the wrong message, so those signatures fail on chain.
- **Does a format add or remove a risk?** No device-side difference: same bytes. Host side, every candidate format carries the previous transactions, which is what lets the device check amounts and fee; today's Neuron fetches them by RPC when its file lacks them ([ledger.ts L78](https://github.com/nervosnetwork/neuron/blob/d3a7467d218e4b6f777326682a83fec802669c00/packages/neuron-wallet/src/services/hardware/ledger.ts#L78)).

## Answer

**The design doesn't block Ledger signing.** A Ledger signed a Sigsheet 2-of-3 genesis multisig through Neuron's own host library on the emulator, and the transaction committed on the devnet; the device received the same bytes from C, B and A. **The Ledger app is the limit, not the format:** 0.6.3 signs only the genesis multisig deployment, refuses the v2 and 2024 locks and PR #34's shape (and quits when it refuses), and can sign v2 only blind. No drawback from choosing the emulator was found for the questions it can answer; the device timing and the watchdog stay open until a run on hardware.
