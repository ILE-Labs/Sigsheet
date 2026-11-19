# XQ14: can a Ledger sign a Sigsheet multisig transaction? (on Ledger's emulator)

**Question:** does the design block Ledger signing through Neuron, or any hardware wallet? Tested on Ledger's open-source emulator, Speculos, with the emulator's own default test seed: no device and no real keys. Also:
1. what the emulator's result proves about a real device, and what it doesn't;
2. what a signer goes through on the device under each candidate format, compared with today's Neuron Ledger path;
3. what the device shows and checks before signing, whether anything is signed blind, and whether a format adds or removes a risk.

**Answer** (design-stage; [results.md](results.md)): the design doesn't block Ledger signing; the limits are those of Ledger's Nervos app 0.6.3, not of the format.

## Rules this experiment follows

- No sudo, and nothing installed system-wide: every tool lives under `refs/_ledger/` at the repository root (git-ignored) and is pinned below.
- Only the emulator's default test seed ([`speculos/main.py` L60-L62](https://github.com/LedgerHQ/speculos/blob/82fbd97a91ffcf1fbf9eb0201a95b70c09dfe921/speculos/main.py#L60-L62)); no device, no real keys. The seed isn't written anywhere in this branch: Speculos uses it when no other is given.
- Only the local devnet; nothing is sent to any other network.

## Environment and exact versions

| Item | Version | Where |
|---|---|---|
| Ledger Nervos app | `app-nervos` master `8c50034c8109f90d87c2b3c413361ef83f5b2e03` (2026-08-21), app version 0.6.3. Also read: `9922a20ce0cccdb09c8d3a7a14062865885d3466` (2024-08-08, app 0.6.0), the commit linked in [neuron#3095](https://github.com/nervosnetwork/neuron/issues/3095) | `refs/app-nervos` |
| Ledger SDK | `ledger-secure-sdk` tag v26.6.1 = `473fe57b98c24ce9488b1dfecd51ad92fe665d19` (API level 26; the SDK the app's 0.6.3 release tags name) | `refs/_ledger/ledger-secure-sdk` |
| Emulator | Speculos 0.27.6 from PyPI (git tag v0.27.6 = `82fbd97a91ffcf1fbf9eb0201a95b70c09dfe921`), in a venv on Python 3.14.4. Its GUI dependencies (pyqt6, pygame) are left out; it runs headless | `refs/_ledger/venv`; exact package versions in `venv-freeze.txt` |
| qemu | `qemu-user` 1:10.2.1+ds-1ubuntu3.3 (`qemu-arm`, static-pie), linked as `qemu-arm-static`, the name Speculos runs | `refs/_ledger/root`, `refs/_ledger/bin` |
| Compiler and linker | clang 21.1.8 (`clang-21` 1:21.1.8-6ubuntu1, from the system); `lld-21` and `liblld-21` 1:21.1.8-6ubuntu1 | `refs/_ledger/root`, `refs/_ledger/bin/ld.lld` |
| C library headers for the ARM target | `libnewlib-arm-none-eabi` and `libnewlib-dev` 4.6.0.20260123-1 | `refs/_ledger/root/usr/lib/arm-none-eabi` |

The `.deb` packages are Ubuntu 26.04's, downloaded with `apt-get download` (which needs no root) and unpacked with `dpkg-deb -x`; nothing is installed system-wide. Their SHA-256 sums are in `debs-SHA256SUMS`.

## Exact commands

From the repository root:

```sh
# 1. Tools (log in results/setup.log)
git clone https://github.com/LedgerHQ/app-nervos refs/app-nervos && git -C refs/app-nervos checkout 8c50034c8109f90d87c2b3c413361ef83f5b2e03
git clone --depth 1 --branch v26.6.1 https://github.com/LedgerHQ/ledger-secure-sdk refs/_ledger/ledger-secure-sdk
sh experiments/XQ14/scripts/setup_tools.sh
#    To reinstall the Python side exactly: refs/_ledger/venv/bin/pip install --no-deps -r experiments/XQ14/venv-freeze.txt

# 2. Build the app for the Nano S Plus (target nanos2) from a copy of the pinned source
mkdir -p refs/_ledger/app-work/app-nervos-8c50034 refs/_ledger/sysroot
git -C refs/app-nervos archive 8c50034c8109f90d87c2b3c413361ef83f5b2e03 | tar -x -C refs/_ledger/app-work/app-nervos-8c50034
ln -sfn ../root/usr/include/newlib refs/_ledger/sysroot/include
ln -sfn ../root/usr/lib/arm-none-eabi/newlib refs/_ledger/sysroot/lib
cp experiments/XQ14/scripts/build.sh refs/_ledger/app-work/ && sh refs/_ledger/app-work/build.sh
mkdir -p experiments/XQ14/bin && cp "$(find refs/_ledger/app-work/app-nervos-8c50034 -path '*nanos2/bin/app.elf')" experiments/XQ14/bin/nervos-0.6.3-8c50034-nanos2.elf
#    The build stops at its last step (app.apdu, which needs ledgerblue to load a physical device); app.elf is
#    complete. Its SHA-256 is in bin/SHA256SUMS. The binary itself isn't in this branch (build output). The app
#    reports "hash 8713fdf7" because its build reads the git commit of the enclosing folder, not app-nervos's.

# 3. Bind Speculos to 127.0.0.1 (it binds 0.0.0.0 by default): apply the 5-line change in speculos-localhost.diff
(cd refs/_ledger/venv/lib/python3.14/site-packages && patch -p1 < ../../../../../../experiments/XQ14/speculos-localhost.diff)
#    Start it (the runners do this per run):
PATH=$PWD/refs/_ledger/bin:$PATH refs/_ledger/venv/bin/speculos --model nanosp --display headless \
  --apdu-port 9999 --api-port 5000 experiments/XQ14/bin/nervos-0.6.3-8c50034-nanos2.elf

# 4. The host side: Neuron's host library and Ledger's Speculos transport, pinned (client/package-lock.json)
(cd experiments/XQ14/client && npm_config_cache=$PWD/../../../refs/_npm-cache npm install --ignore-scripts)
(cd experiments/XQ14/client && node pubkey.js > ../results/pubkey-path0.json)   # the device key at m/44'/309'/0'/0/0

# 5. The runs (need X1's devnet and the cells funded by experiments/X5/scripts/fund_s4.py)
cd experiments/XQ14
python3 -I -X utf8 scripts/run_ledger.py genesis-member v2-member 2024-member genesis-nonmember \
  multisig-plus-single-key two-inputs-one-group six-outputs v2-member-contract-data v2-blind-hash
python3 -I -X utf8 -c "import sys; sys.path.insert(0,'scripts'); import run_ledger as r; \
  r.run_case_file('pr34-replay-default','R1-fiber-scripts-pr34.json'); \
  r.run_case_file('pr34-replay-contract-data','R1-fiber-scripts-pr34.json',['Allow contract data']); \
  r.run_case_file('dao-payout-replay','R2-dao-payout.json')"                  # needs the mainnet inputs
python3 -I -X utf8 scripts/probe_sizes.py > results/size-probes.json
```

`scripts/run_ledger.py` restarts Speculos before each run (a refused transaction makes the 0.6.3 app exit), changes the device settings through Speculos's REST API when a run needs it, signs with `client/sign.js` (which records every screen and presses right until "Accept", then both buttons), checks the signature against the lock's message computed by the prototypes, adds s1's signature, finalizes, dry-runs and sends on the devnet. The first run (`genesis-member`) shared one emulator session with the first `v2-member` attempt; that log is `results/speculos/v2-member-first-try.log`.

## Files

- `scripts/`: `setup_tools.sh`, `build.sh`, `job.py` (Sigsheet file to device job), `run_ledger.py`, `probe_sizes.py`; `client/`: `pubkey.js`, `sign.js`.
- `bin/SHA256SUMS` (the built app's hash; the binary is build output and isn't kept), `venv-freeze.txt`, `debs-SHA256SUMS`.
- `speculos-localhost.diff`: the change to Speculos 0.27.6, with Speculos's license in [`NOTICE.md`](NOTICE.md).
- `results/`: `runs/<run>/` (Sigsheet files in C, B+w and A, `job.json`, `device.json`, `result.json`), `probes/`, `size-probes.json`, `speculos/` (emulator logs), `setup.log`. The app's build logs aren't kept: they are compiler output full of the build machine's paths; the built app's SHA-256 is in `bin/SHA256SUMS`. The three replays of mainnet transactions (`runs/pr34-replay-*`, `runs/dao-payout-replay` and their logs) are mainnet inputs ([mainnet-inputs.md](../mainnet-inputs.md)).
