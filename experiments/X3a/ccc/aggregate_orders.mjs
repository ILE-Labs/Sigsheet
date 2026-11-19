// X3a step 2: CCC (@ckb-ccc/core 1.23.1) aggregateTransactions on PR #34's five one-signature partial
// transactions, in all 120 orders.
//
// Usage, from experiments/X3a:  node ccc/aggregate_orders.mjs results/partials.json results/ccc-orders.json
//
// Offline, as in X1: the input cells come from X1's case file into CCC's client cache, and the RPC URL
// points at a closed local port. The multisig signer is CCC's own SignerMultisigCkbReadonly for the PR's
// 3-of-5 v2 lock. For each order, the script records which members' signatures CCC kept (by matching the
// signature bytes), the bytes of both witnesses, and whether the single-key input's signature survived.
import { ccc } from "@ckb-ccc/core";
import { JsonRpcTransformers } from "@ckb-ccc/core/advanced";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const [partialsFile, outFile] = process.argv.slice(2);
const here = path.dirname(fileURLToPath(import.meta.url));
const d = JSON.parse(fs.readFileSync(partialsFile, "utf8"));
const kase = JSON.parse(fs.readFileSync(path.join(here, "..", "..", "X1", "cases", "R1-fiber-scripts-pr34.json"), "utf8"));
const DEAD = "http://127.0.0.1:9/";
const scriptOf = (s) => ccc.Script.from({ codeHash: s.code_hash, hashType: s.hash_type, args: s.args });

const client = new ccc.ClientPublicMainnet({ url: DEAD });
await client.cache.recordCells(kase.input_cells.map((ic) => ccc.Cell.from({
  outPoint: { txHash: ic.out_point.tx_hash, index: ic.out_point.index },
  cellOutput: { capacity: ic.output.capacity, lock: scriptOf(ic.output.lock), type: ic.output.type ? scriptOf(ic.output.type) : undefined },
  outputData: ic.data,
})));
const g = kase.groups.find((x) => x.kind === "multisig");
const ro = new ccc.SignerMultisigCkbReadonly(client,
  { publicKeyHashes: g.multisig.key_hashes, threshold: g.multisig.threshold, mustMatch: g.multisig.require_first_n },
  { scriptInfos: [{ codeHash: g.lock.code_hash, hashType: g.lock.hash_type, cellDeps: [] }] });

const partials = d.partials.map((p) => ({ member: p.member, tx: JsonRpcTransformers.transactionTo(p.tx) }));
const sigToMember = Object.fromEntries(Object.entries(d.signatures_by_member).map(([m, v]) => [v.signature, Number(m)]));
const scriptLen = 4 + 20 * g.multisig.key_hashes.length;

function* permutations(a) {
  if (a.length <= 1) { yield a; return; }
  for (let i = 0; i < a.length; i++) for (const p of permutations([...a.slice(0, i), ...a.slice(i + 1)])) yield [a[i], ...p];
}

const runs = [];
for (const order of permutations(partials)) {
  const merged = await ro.aggregateTransactions(order.map((p) => p.tx.clone()));
  const lock = ccc.bytesFrom(merged.getWitnessArgsAt(0).lock);
  const sigs = [];
  for (let off = scriptLen; off < lock.length; off += 65) sigs.push(ccc.hexFrom(lock.slice(off, off + 65)));
  runs.push({
    order: order.map((p) => p.member),
    kept_members: sigs.map((s) => sigToMember[s] ?? (/^0x0+$/.test(s) ? "empty" : "unknown")),
    lock_bytes: lock.length,
    witness0: ccc.hexFrom(merged.witnesses[0]),
    witness1: ccc.hexFrom(merged.witnesses[1]),
    single_key_signature_kept: ccc.hexFrom(merged.witnesses[1]) === d.single_key_witness_signed,
    tx_hash_unchanged: merged.hash() === d.tx_hash,
  });
}
fs.writeFileSync(outFile, JSON.stringify({ tool: "@ckb-ccc/core 1.23.1 aggregateTransactions", orders: runs.length, runs }, null, 1));
console.log(`${runs.length} orders aggregated -> ${outFile}`);
