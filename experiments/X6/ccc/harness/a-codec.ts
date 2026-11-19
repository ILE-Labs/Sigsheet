// X6: does CCC's path-A layer produce the same building packet as the Python prototype, for every X2 case?
import core from "../core/src/index.js";
import * as bpRaw from "../core/src/sigsheet/buildingPacket.js";
const bp = ((bpRaw as any).default ?? bpRaw) as any;
import fs from "node:fs";
const { ccc } = core as unknown as { ccc: typeof import("../core/src/index.js").ccc };
const dir = process.argv[2];
const results: Record<string, unknown> = {};
for (const f of fs.readdirSync(dir).filter((x) => x.endsWith(".c.json")).sort()) {
  const sheet = ccc.Sigsheet.fromJson(fs.readFileSync(`${dir}/${f}`, "utf8"), ["0x6283a479a3cf5d4276cd93594de9f1827ab9b55c7b05b3d28e4c2e0a696cfefd/type"]);
  const client = new ccc.ClientPublicTestnet({ url: "http://127.0.0.1:9/" });
  await sheet.recordContext(client);
  const groups = [...(await sheet.groups(client)).values()].map((g) => ({
    lockHash: g.lockHash, kind: g.kind, inputs: g.inputs, codeHash: g.script.codeHash, hashType: g.script.hashType,
    args: g.script.args }));
  const mine = (bp as any).sigsheetToBuildingPacket(sheet.doc, groups).slice(2);
  const python = fs.readFileSync(`${dir}/${f.replace(".c.json", ".a.hex")}`, "utf8").trim();
  let parts = "ok";
  try { (bp as any).buildingPacketToParts("0x" + python); } catch (e) { parts = String(e); }
  results[f] = { same_bytes_as_python: mine === python, bytes: python.length / 2, decode_checks: parts };
}
console.log(JSON.stringify(results, null, 1));
