// X1 side check: does ccc.Transaction.from accept the `transaction` object of a ckb-cli tx file
// (snake_case, as the CKB RPC writes it) directly, and give the right hash?
// Usage, from experiments/X1/ccc:  node ckbcli-json-from.mjs ../results/ckb-cli/S3-v2-2of3-two-inputs.json ../cases/S3-v2-2of3-two-inputs.json
import { ccc } from "@ckb-ccc/core";
import fs from "node:fs";
const file = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const kase = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const out = { expected_hash: kase.tx_hash };
try {
  const tx = ccc.Transaction.from(file.transaction);
  out.parsed = true;
  out.hash = tx.hash();
  out.same_hash = out.hash === kase.tx_hash;
  out.inputs = tx.inputs.length;
  out.first_input_previous_output = tx.inputs[0]?.previousOutput;
  out.cell_deps = tx.cellDeps.map((d) => ({ txHash: d.outPoint.txHash, index: Number(d.outPoint.index), depType: d.depType }));
} catch (e) {
  out.parsed = false;
  out.error = String(e).slice(0, 300);
}
console.log(JSON.stringify(out, null, 1));
