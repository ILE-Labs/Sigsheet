#!/bin/sh
# XQ14 step 1: put the Ledger emulator and the app's build tools in refs/_ledger/, without sudo.
# Nothing is installed system-wide: .deb packages are downloaded with `apt-get download` (no root needed)
# and unpacked with `dpkg-deb -x` into refs/_ledger/root; Python packages go into refs/_ledger/venv.
# The system's clang 21 (already installed) compiles the app; lld-21 (same LLVM build) links it.
# Run from the repository root:  sh experiments/XQ14/scripts/setup_tools.sh
set -eu
L="$PWD/refs/_ledger"
mkdir -p "$L/debs" "$L/root" "$L/bin"
cd "$L/debs"
# Exact package versions (Ubuntu 26.04 archive, fetched 2026-11-18).
for p in qemu-user=1:10.2.1+ds-1ubuntu3.3 \
         lld-21=1:21.1.8-6ubuntu1 liblld-21=1:21.1.8-6ubuntu1 \
         libnewlib-arm-none-eabi=4.6.0.20260123-1 libnewlib-dev=4.6.0.20260123-1; do
  apt-get download "$p"
done
sha256sum *.deb > SHA256SUMS
for d in *.deb; do dpkg-deb -x "$d" "$L/root"; done
ln -sf "$L/root/usr/bin/qemu-arm" "$L/bin/qemu-arm-static"
ln -sf "$L/root/usr/lib/llvm-21/bin/lld" "$L/bin/ld.lld"
# Speculos 0.27.6, pinned, and its runtime dependencies within its own version bounds; its GUI dependencies
# (pyqt6, pygame) are left out: the emulator runs headless here. The exact versions installed are
# recorded in venv-freeze.txt (reinstall with: pip install --no-deps -r venv-freeze.txt).
python3 -m venv "$L/venv"
"$L/venv/bin/pip" install -q --no-deps speculos==0.27.6
"$L/venv/bin/pip" install -q "construct>=2.10.56,<3" "flask>=2.0.0,<3" "flask-restful>=0.3.9,<1" "flask-cors>=5,<7" \
  "jsonschema>=3.2.0,<5" "mnemonic>=0.19,<1" "pillow>=13,<14" "pyelftools>=0.27,<1" "requests>=2.25.1,<3" "ledgered>=0.14.0"
"$L/venv/bin/pip" freeze > "$L/venv-freeze.txt"
echo "setup done"
