# X4 results: attacks, the checks that catch them, and the high-s twin on chain

Conditions (design-stage): 2026-11-18 (UTC); the prototypes; the real genesis 2-of-3 payment (R2) as the base file; the local devnet for the high-s and replay runs. Raw output: `results/`. Commands: `README.md`.

## 1. The lock accepts a malleated signature, on all three deployments (run on chain)

| Deployment | Control (both low-s), dry run | s1's signature replaced by its high-s twin | Both replaced, dry run |
|---|---|---|---|
| genesis (`type`) | accepted | accepted and **committed**: `0xc2e31b41…`, block 15,486 | accepted |
| 2024 (`type`) | accepted | accepted and **committed**: `0x0d20e97b…`, block 15,489 | accepted |
| v2 (`data1`) | accepted | accepted and **committed**: `0x30e59afd…`, block 15,493 | accepted |

The committed witness holds the high-s bytes (`committed_witness_equals_twin`, `results/high-s-devnet.json`). This confirms on chain what X3a found by reading the lock's secp256k1: one member can have two valid signatures with different bytes. So a merge rule must choose deterministically: the design's rule normalizes to low-s and keeps the smaller bytes. BIP-174's "pick arbitrarily" and PCZT's "fail on conflict" don't (X3a: 715 and 1,531 of 2,000 trials).

## 2. Each attack, in each format

| Attack | C | B+w | A | The check that catches it |
|---|---|---|---|---|
| 1. Falsified input cell: the spent cell's capacity raised by 1,000,000 CKB in the carried previous transaction (BIP-174's fee attack) | refused | refused | refused | The previous transaction no longer hashes to the input's out point (C: its context key; B, A: the input's out point) |
| 1b. A only: `resolved_inputs` raised, `input_transactions` intact | | | refused | Profile check: `resolved_inputs.outputs[0]` must equal the carried previous transaction's output. **A CoBuild reader that doesn't know the profile would show a fee of 1,000,000.00001186 CKB** instead of 0.00001186 |
| 2-3. Swapped transaction or altered outputs, the original signatures kept | both signatures dropped; not ready | same | same | Signatures are verified against the file's own message; merging it with an honest file is refused: "files describe different unsigned transactions" |
| 4. A valid signature by a non-member | dropped | dropped | dropped | Recovered key not in the config |
| 5. Junk: random bytes, a high-s twin, a signature filed under the wrong member | junk dropped, twin normalized; **still finalizes**, same transaction | same | same (A can't even hold a wrong-length signature) | Verify, members only, key by signer, low-s; merged with the honest file, the result equals the honest file |
| 6a. Replay: a committed transaction sent again | rejected on devnet: `TransactionFailedToResolve` (its input is spent) | | | The chain |
| 6b. Replay: valid signatures put on another transaction (same multisig, fresh cell) | rejected on devnet: lock error -52 | | | The message covers the transaction hash, which covers the out points |
| 6c. B's network id changed | | accepted, still valid | | Nothing: the id isn't signed. It is only a display hint |
| 7. Multisig config swapped for the attacker's keys | refused | refused | refused | The config must hash to the lock args |
| 9. A display field: C `description`; B a proprietary note; A a `change_output` | refused (unknown field) | refused (not canonical) | refused (profile) | Strict schema; A's profile forbids `change_output` and a non-empty `message` |
| 10. A witness the message covers changed after two members signed | both signatures dropped | same | same | The message covers every witness of the group and every witness beyond the inputs |

Every honest file is accepted, finalizes, and passes the lock's rules (`honest` in `results/x4.json`).

## Answer

Every attack is caught in all three formats, by four checks that every format has in common: previous transactions by hash, the config by hash, signatures by the lock's own message and membership, and a deterministic merge. Path A needs one more check (`resolved_inputs` against the previous transactions) and is safe only in tools that know its profile: a generic CoBuild wallet reading `resolved_inputs` would show a falsified fee. B's network id adds no protection, because it isn't signed. The lock accepts high-s twins on chain, which is why the merge must normalize.
