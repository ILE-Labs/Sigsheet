// X3a step 5: does CCC's signature recovery (used by aggregateTransactions) accept a signature's malleated
// high-s twin? Usage, from experiments/X3a:  node ccc/high_s.mjs results/partials.json results/high-s.json
import { ccc } from "@ckb-ccc/core";
import fs from "node:fs";
const [inFile, outFile] = process.argv.slice(2);
const d = JSON.parse(fs.readFileSync(inFile, "utf8"));
const N = BigInt("0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141");
const out = [];
for (const [m, v] of Object.entries(d.signatures_by_member)) {
  const sig = ccc.bytesFrom(v.signature);
  const s = BigInt(ccc.hexFrom(sig.slice(32, 64)));
  const twin = new Uint8Array(65);
  twin.set(sig.slice(0, 32), 0);
  twin.set(ccc.bytesFrom("0x" + (N - s).toString(16).padStart(64, "0")), 32);
  twin[64] = sig[64] ^ 1;
  const rec = (x) => { try { return ccc.hashCkbShort(ccc.Signer && ccc.recoverMessageSecp256k1 ? ccc.recoverMessageSecp256k1(d.message, x) : null); } catch (e) { return "error: " + String(e).slice(0, 80); } };
  out.push({ member: Number(m), original_low_s: s <= N / 2n, original_recovers_to: rec(ccc.hexFrom(sig)), twin_recovers_to: rec(ccc.hexFrom(twin)), member_key_hash: v.key_hash });
}
fs.writeFileSync(outFile, JSON.stringify(out, null, 1));
console.log(JSON.stringify(out.map((o) => [o.member, o.original_low_s, o.twin_recovers_to === o.member_key_hash])));
