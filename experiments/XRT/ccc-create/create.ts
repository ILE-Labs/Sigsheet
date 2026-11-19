// XRT-4: creating a Sigsheet file inside CCC. Separate from X6's measured patch, which it
// imports unchanged. A CCC transaction becomes a Sigsheet file: each input's previous transaction (raw part) is
// fetched through the client (the one step that needs a node), the first witness of each group the file signs
// becomes a template, and the multisig configs the groups use are added. The result is re-read by the strict
// reader. Outputs with no type script are written "type": null (the canonical form ckb-cli and the prototype use).
import core from "../../X6/ccc/core/src/index.js";
const { ccc } = core as unknown as { ccc: typeof import("../../X6/ccc/core/src/index.js").ccc };
type Client = import("../../X6/ccc/core/src/index.js").ccc.Client;
type SigsheetConfig = { public_key_hashes: string[]; require_first_n: number; threshold: number };

function nullTypes<T extends { outputs: unknown[] }>(t: T): T {
  return { ...t, outputs: t.outputs.map((o: any) => (o.type ? o : { ...o, type: null })) };
}

export async function createSigsheet(
  txLike: any,
  client: Client,
  configs: SigsheetConfig[],
  extraMultisig: string[] = [],
): Promise<any> {
  const tx = ccc.Transaction.from(txLike);
  const context: Record<string, any> = {};
  for (const input of tx.inputs) {
    const h = input.previousOutput.txHash;
    if (context[h]) continue;
    const res = await client.getTransaction(h);
    if (!res) throw new Error(`previous transaction ${h} not found`);
    const { witnesses: _w, ...raw } = nullTypes(ccc.Sigsheet.toRpcTransaction(res.transaction));
    context[h] = raw;
  }
  const rpcTx = nullTypes(ccc.Sigsheet.toRpcTransaction(tx));
  const witnesses = [...rpcTx.witnesses];
  while (witnesses.length < tx.inputs.length) witnesses.push("0x");
  const multisig_configs: Record<string, SigsheetConfig> = {};
  for (const cfg of configs) {
    const script = new Uint8Array([
      0, cfg.require_first_n, cfg.threshold, cfg.public_key_hashes.length,
      ...cfg.public_key_hashes.flatMap((k) => [...ccc.bytesFrom(k)]),
    ]);
    multisig_configs[ccc.hashCkbShort(script)] = cfg;
  }
  const doc: any = { version: "0x1", transaction: { ...rpcTx, witnesses }, context, multisig_configs, signatures: {} };
  const sheet = new ccc.Sigsheet(doc, extraMultisig);
  await sheet.recordContext(client);
  const used = new Set<string>();
  for (const g of (await sheet.groups(client)).values()) {
    if (g.kind === "unknown") continue;
    if (g.kind === "multisig") used.add(g.script.args.slice(0, 42));
    const i = g.inputs[0];
    const w = doc.transaction.witnesses[i];
    if (w && w !== "0x") {
      const wa = ccc.WitnessArgs.fromBytes(w);
      wa.lock = undefined;
      doc.transaction.witnesses[i] = wa.inputType || wa.outputType ? ccc.hexFrom(wa.toBytes()) : "0x";
    }
  }
  for (const k of Object.keys(doc.multisig_configs)) if (!used.has(k)) delete doc.multisig_configs[k];
  return ccc.Sigsheet.fromJson(sheet.toJson(), extraMultisig);
}
