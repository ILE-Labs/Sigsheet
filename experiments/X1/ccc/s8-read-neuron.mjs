// X1, case S8: can CCC read Neuron's offline JSON as it is? Offline; reports what Transaction.from does with it.
// Usage, from experiments/X1/ccc:  node s8-read-neuron.mjs ../results/neuron-export/S8-neuron-export-after-first-signature.json
import { ccc } from "@ckb-ccc/core";
import fs from "node:fs";
const exp = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = {};
try {
  const tx = ccc.Transaction.from(exp.transaction);
  out.parsed = true;
  out.hash = tx.hash();
  out.witness0 = tx.witnesses[0];
} catch (e) {
  out.parsed = false;
  out.error = String(e).slice(0, 300);
}
console.log(JSON.stringify(out, null, 1));
