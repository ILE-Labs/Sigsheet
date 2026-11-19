// X1, implementation C: CCC (@ckb-ccc/core 1.23.1) computes the signing message of every lock group,
// signs with the designated test keys, and merges the signed copies with aggregateTransactions.
//
// Usage, from experiments/X1:  node ccc/x1-ccc.mjs cases ../../keys/x1/keys.json results/ccc.json
//
// Offline on purpose: every input cell comes from the case file into CCC's client cache, and the
// client's RPC URL points at a closed local port, so any network call CCC tried would fail loudly.
// Multisig groups go through SignerMultisigCkbReadonly.getSignInfo (the message CCC's multisig
// signer signs); single-key groups through Transaction.getSignHashInfo (what SignerCkbPrivateKey uses).
import { ccc } from "@ckb-ccc/core";
import { JsonRpcTransformers } from "@ckb-ccc/core/advanced";
import fs from "node:fs";
import path from "node:path";

const [casesDir, keysFile, outFile] = process.argv.slice(2);
const keys = Object.fromEntries(JSON.parse(fs.readFileSync(keysFile, "utf8")).map((k) => [k.name, k]));
const DEAD = "http://127.0.0.1:9/";

const scriptOf = (s) => ccc.Script.from({ codeHash: s.code_hash, hashType: s.hash_type, args: s.args });

async function clientFor(c) {
  const client = c.network === "mainnet" ? new ccc.ClientPublicMainnet({ url: DEAD }) : new ccc.ClientPublicTestnet({ url: DEAD });
  await client.cache.recordCells(
    c.input_cells.map((ic) =>
      ccc.Cell.from({
        outPoint: { txHash: ic.out_point.tx_hash, index: ic.out_point.index },
        cellOutput: { capacity: ic.output.capacity, lock: scriptOf(ic.output.lock), type: ic.output.type ? scriptOf(ic.output.type) : undefined },
        outputData: ic.data,
      }),
    ),
  );
  return client;
}

function multisigOptions(g) {
  const info = { publicKeyHashes: g.multisig.key_hashes, threshold: g.multisig.threshold, mustMatch: g.multisig.require_first_n };
  const since = g.since_in_args == null ? undefined : ccc.Since.from({ relative: "absolute", metric: "blockNumber", value: g.since_in_args });
  const options = { since, scriptInfos: [{ codeHash: g.lock.code_hash, hashType: g.lock.hash_type, cellDeps: [] }] };
  return { info, options };
}

const out = { tool: "@ckb-ccc/core 1.23.1", messages: {}, signatures: {}, signed_witnesses: {}, aggregated: {}, checks: {}, errors: {} };
const put = (obj, a, b, k, v) => { obj[a] ??= {}; obj[a][b] ??= {}; if (k === null) obj[a][b] = v; else obj[a][b][k] = v; };

for (const f of fs.readdirSync(casesDir).filter((f) => f.endsWith(".json")).sort()) {
  const c = JSON.parse(fs.readFileSync(path.join(casesDir, f), "utf8"));
  const client = await clientFor(c);
  const tx = JsonRpcTransformers.transactionTo(c.tx);
  put(out.checks, c.id, "tx_hash_matches", null, tx.hash() === c.tx_hash);
  for (const g of c.groups) {
    try {
      const lock = scriptOf(g.lock);
      if (g.kind === "multisig") {
        const { info, options } = multisigOptions(g);
        const ro = new ccc.SignerMultisigCkbReadonly(client, info, options);
        const derived = (await ro.scriptInfos)[0].script;
        put(out.checks, c.id, `${g.name}: CCC derives the same lock args`, null, derived.args === g.lock.args);
        const si = await ro.getSignInfo(tx, lock);
        put(out.messages, c.id, g.name, null, si.message);
        const copies = [];
        for (const k of g.signers ?? []) {
          const s = new ccc.SignerMultisigCkbPrivateKey(client, keys[k].secret, info, options);
          // Each signer signs its own copy of the unsigned transaction. Transaction.from returns an
          // existing Transaction instance unchanged, and signing fills it in place, so clone first.
          const signed = await s.signOnlyTransaction(tx.clone());
          const w = signed.getWitnessArgsAt(si.position);
          put(out.signed_witnesses, c.id, g.name, k, ccc.hexFrom(signed.witnesses[si.position]));
          const scriptLen = 4 + 20 * g.multisig.key_hashes.length;
          const sigs = ccc.bytesFrom(w.lock).slice(scriptLen);
          put(out.signatures, c.id, g.name, k, ccc.hexFrom(sigs.slice(0, 65)));
          copies.push(signed);
        }
        if (copies.length) {
          const merged = await ro.aggregateTransactions(copies);
          put(out.aggregated, c.id, g.name, null, ccc.hexFrom(merged.witnesses[si.position]));
        }
      } else {
        const si = await tx.getSignHashInfo(lock, client);
        put(out.messages, c.id, g.name, null, si.message);
        for (const k of g.signers ?? []) {
          if (!keys[k]) continue;
          const s = new ccc.SignerCkbPrivateKey(client, keys[k].secret);
          const signed = await s.signOnlyTransaction(tx.clone());
          const w = signed.getWitnessArgsAt(si.position);
          put(out.signatures, c.id, g.name, k, ccc.hexFrom(w.lock));
        }
      }
    } catch (e) {
      put(out.errors, c.id, g.name, null, String(e && e.stack ? e.stack.split("\n").slice(0, 3).join(" | ") : e));
    }
  }
}
fs.writeFileSync(outFile, JSON.stringify(out, null, 1));
for (const [cid, gs] of Object.entries(out.messages)) for (const [g, m] of Object.entries(gs)) console.log(cid.padEnd(30), g.padEnd(24), m);
console.log("errors:", JSON.stringify(out.errors));
console.log("checks:", JSON.stringify(out.checks));
