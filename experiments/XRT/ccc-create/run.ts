// XRT-4 runner:  tsx run.ts create <spec.json> <out.json> <rpc url> [devnet]
// spec: { inputs: [{txHash, index}], outputs: [{capacity, lock: {codeHash, hashType, args}}], cellDeps: [...],
//         configs: [{public_key_hashes, require_first_n, threshold}] }. CCC builds the transaction from the spec.
import core from "../../X6/ccc/core/src/index.js";
const { ccc } = core as unknown as { ccc: typeof import("../../X6/ccc/core/src/index.js").ccc };
import fs from "node:fs";
import { createSigsheet } from "./create.js";

const DEVNET_2024 = "0x6283a479a3cf5d4276cd93594de9f1827ab9b55c7b05b3d28e4c2e0a696cfefd/type";
const [cmd, specFile, out, url, net] = process.argv.slice(2);
if (cmd !== "create") throw new Error("usage: run.ts create <spec.json> <out.json> <rpc url> [devnet]");
const spec = JSON.parse(fs.readFileSync(specFile, "utf8"));
const tx = ccc.Transaction.from({
  inputs: spec.inputs.map((o: any) => ({ previousOutput: o })),
  outputs: spec.outputs,
  outputsData: spec.outputs.map(() => "0x"),
  cellDeps: spec.cellDeps,
});
const client = new ccc.ClientPublicTestnet({ url });
const t0 = performance.now();
const sheet = await createSigsheet(tx, client, spec.configs, net === "devnet" ? [DEVNET_2024] : []);
fs.writeFileSync(out, sheet.toJson());
console.log(JSON.stringify({ cmd, out, inputs: tx.inputs.length, ms: Math.round(performance.now() - t0) }));
