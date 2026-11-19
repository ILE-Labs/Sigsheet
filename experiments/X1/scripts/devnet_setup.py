#!/usr/bin/env python3
"""Make the X1 devnet chain spec from a fresh `ckb init --chain dev` folder. This is the edit X1 used.

Usage, from experiments/X1, after:
    ckb init --chain dev -C ../../devnet/node --ba-arg <k0 blake160> \
      --ba-code-hash 0x9bd7e06f3ecf4be0f2fcd2188b23f1b9fcc88e5d4b65a8637b17723bbda3cce8 --ba-hash-type type --ba-message 0x
then:
    python3 -I -X utf8 scripts/devnet_setup.py ../../devnet/node
It copies the 2024 and v2 multisig binaries (data/mainnet/multisig-2024.bin, multisig-v2.bin, read from
mainnet cells by fetch_mainnet.py) into specs/cells/, adds them as genesis system cells with two dep
groups, replaces the issued cells with the fresh X1 keys, binds P2P to 127.0.0.1, turns on the
Indexer RPC, sets 1-second dummy mining, and saves a copy of the spec to data/devnet/dev.toml.
"""
import json
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent.parent
node = pathlib.Path(sys.argv[1]).resolve()
(node / "specs" / "cells").mkdir(parents=True, exist_ok=True)
for name in ("multisig-2024.bin", "multisig-v2.bin"):
    shutil.copy(HERE / "data" / "mainnet" / name, node / "specs" / "cells" / name)

p = node / "specs" / "dev.toml"
t = p.read_text()
t = t.replace('''[[genesis.system_cells]]
file = { bundled = "specs/cells/secp256k1_blake160_multisig_all" }
create_type_id = true
capacity = 100_000_0000_0000
''', '''[[genesis.system_cells]]
file = { bundled = "specs/cells/secp256k1_blake160_multisig_all" }
create_type_id = true
capacity = 100_000_0000_0000
# X1: the 2024 multisig deployment, binary copied from mainnet cell 0x0a13d8d9...455d8:0 (type id, as on mainnet)
[[genesis.system_cells]]
file = { file = "cells/multisig-2024.bin" }
create_type_id = true
capacity = 100_000_0000_0000
# X1: the v2 multisig deployment, binary copied from mainnet cell 0x3e27a1a2...fa282:0 (referenced by data1 hash, as on mainnet)
[[genesis.system_cells]]
file = { file = "cells/multisig-v2.bin" }
create_type_id = false
capacity = 100_000_0000_0000
''')
t = t.replace('''# For first 11 block''', '''[[genesis.dep_groups]]
name = "multisig_2024"
files = [
  { bundled = "specs/cells/secp256k1_data" },
  { file = "cells/multisig-2024.bin" },
]
[[genesis.dep_groups]]
name = "multisig_v2"
files = [
  { bundled = "specs/cells/secp256k1_data" },
  { file = "cells/multisig-v2.bin" },
]

# For first 11 block''')
keys = json.loads((HERE / "../../keys/x1/keys.json").read_text())
start = t.index("# issue for random generated private key: d00c06")
end = t.index("[params]")
issued = "".join(f'''# X1 fresh test key {k["name"]}
[[genesis.issued_cells]]
capacity = 100_000_000_00000000
lock.code_hash = "0x9bd7e06f3ecf4be0f2fcd2188b23f1b9fcc88e5d4b65a8637b17723bbda3cce8"
lock.args = "{k["blake160"]}"
lock.hash_type = "type"

''' for k in keys)
p.write_text(t[:start] + issued + t[end:])

c = node / "ckb.toml"
ct = c.read_text()
ct = ct.replace('listen_addresses = ["/ip4/0.0.0.0/tcp/8115"]', 'listen_addresses = ["/ip4/127.0.0.1/tcp/8115"]')
ct = ct.replace('"Debug", "Terminal"]', '"Debug", "Indexer", "Terminal"]')
c.write_text(ct)
m = node / "ckb-miner.toml"
m.write_text(m.read_text().replace("value = 5000", "value = 1000"))
(HERE / "data" / "devnet").mkdir(parents=True, exist_ok=True)
shutil.copy(p, HERE / "data" / "devnet" / "dev.toml")
print("done:", p)
