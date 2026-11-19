// X6/X5 driver for the patched CCC core: CCC as a Sigsheet tool.
//   tsx sigsheet-ccc.ts sign     <in.json> <out.json> <private key hex> [network]
//   tsx sigsheet-ccc.ts merge    <out.json> <in1.json> <in2.json> ... [network]
//   tsx sigsheet-ccc.ts finalize <in.json> <final-tx.json> [network]     (CKB RPC JSON, ready to send)
//   tsx sigsheet-ccc.ts send     <in.json> <rpc url> [network]           (finalize, then send_transaction)
// Offline for sign, merge and finalize: the input cells come from the file into the client's cache, and the
// client's URL is a closed port, so a network call would fail loudly. "devnet" adds the devnet's 2024 type hash.
import core from "../core/src/index.js";
const { ccc } = core as unknown as { ccc: typeof import("../core/src/index.js").ccc };
import fs from "node:fs";

const DEAD = "http://127.0.0.1:9/";
const DEVNET_2024 = "0x6283a479a3cf5d4276cd93594de9f1827ab9b55c7b05b3d28e4c2e0a696cfefd/type";

function extra(net?: string) {
  return net === "devnet" ? [DEVNET_2024] : [];
}
function client() {
  return new ccc.ClientPublicTestnet({ url: DEAD });
}
function load(f: string, net?: string) {
  return ccc.Sigsheet.fromJson(fs.readFileSync(f, "utf8"), extra(net));
}

const [cmd, ...a] = process.argv.slice(2);
const t0 = performance.now();
if (cmd === "sign") {
  const s = load(a[0], a[3]);
  const n = await s.sign(client(), a[2] as ccc.Hex);
  fs.writeFileSync(a[1], s.toJson());
  console.log(JSON.stringify({ cmd, added: n, ms: Math.round(performance.now() - t0) }));
} else if (cmd === "merge") {
  const net = a.length > 3 && !a[a.length - 1].endsWith(".json") ? a.pop() : undefined;
  const [out, first, ...rest] = a;
  const m = await load(first, net).merge(client(), ...rest.map((f) => load(f, net)));
  fs.writeFileSync(out, m.toJson());
  console.log(JSON.stringify({ cmd, inputs: rest.length + 1, ms: Math.round(performance.now() - t0) }));
} else if (cmd === "finalize" || cmd === "send") {
  const s = load(a[0], cmd === "finalize" ? a[2] : a[2]);
  const tx = await s.finalize(client());
  const json = ccc.Sigsheet.toRpcTransaction(tx);
  if (cmd === "finalize") {
    fs.writeFileSync(a[1], JSON.stringify(json, null, 1));
    console.log(JSON.stringify({ cmd, tx_hash: tx.hash(), ms: Math.round(performance.now() - t0) }));
  } else {
    const rpc = new ccc.ClientPublicTestnet({ url: a[1] });
    const h = await rpc.sendTransaction(tx, "passthrough");
    console.log(JSON.stringify({ cmd, sent: h, ms: Math.round(performance.now() - t0) }));
  }
} else {
  console.error("usage: sign | merge | finalize | send");
  process.exit(2);
}
