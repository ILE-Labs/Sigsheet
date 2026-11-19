// The independent check of the vectors' messages and signatures with CCC's own code (@ckb-ccc/core 1.23.1).
//
// For every vector, from its files alone (never the generator's code):
// - each lock group is found again from the file's context, and must match expected.json's groups;
// - each group's message is computed by CCC: SignerMultisigCkbReadonly.getSignInfo for a multisig group, which also
//   derives the lock args from the config, and Transaction.getSignHashInfo for a single-key group; it must equal
//   expected.json's;
// - each signature a file keeps is recovered with recoverMessageSecp256k1, and blake160 of the key must be the
//   signer it is filed under, a member of its group; each signature a reader drops must fail the same way.
// Offline: every input cell goes into CCC's client cache from the file's context, and the client's RPC URL is a
// closed local port, so any network call would fail.
//
// Usage: node dist/messages.js <vector folder>...   (each folder holds cases/ and attacks/, or vector folders)

import { ccc } from "@ckb-ccc/core";
import { JsonRpcTransformers } from "@ckb-ccc/core/advanced";
import fs from "node:fs";
import path from "node:path";

const CLOSED_PORT = "http://127.0.0.1:9/";

interface Script {
  code_hash: string;
  hash_type: string;
  args: string;
}
interface Output {
  capacity: string;
  lock: Script;
  type: Script | null;
}
interface OutPoint {
  tx_hash: string;
  index: string;
}
interface RawTx {
  inputs: { since: string; previous_output: OutPoint }[];
  outputs: Output[];
  outputs_data: string[];
}
interface Config {
  public_key_hashes: string[];
  require_first_n: number;
  threshold: number;
}
interface Sheet {
  transaction: RawTx & Record<string, unknown>;
  context: Record<string, RawTx>;
  multisig_configs: Record<string, Config>;
  signatures: Record<string, Record<string, string>>;
}
interface Group {
  lock_hash: string;
  kind: string;
  inputs: number[];
  members?: string[];
  require_first_n?: number;
  threshold?: number;
}
interface Expected {
  outcome: string;
  messages?: Record<string, string>;
  dropped?: { group: string; signer: string; reason: string }[];
  shown?: { groups: Group[] };
}

const scriptOf = (s: Script) =>
  ccc.Script.from({
    codeHash: s.code_hash,
    hashType: s.hash_type as ccc.HashType,
    args: s.args,
  });
const blake160 = (hex: string) => ccc.hashCkb(hex).slice(0, 42);
const read = <T>(file: string): T =>
  JSON.parse(fs.readFileSync(file, "ascii")) as T;
const problems: string[] = [];
let checkedMessages = 0;
let checkedSignatures = 0;

function lockOf(sheet: Sheet, i: number): Script {
  const op = sheet.transaction.inputs[i].previous_output;
  return sheet.context[op.tx_hash].outputs[Number(op.index)].lock;
}

async function clientFor(sheet: Sheet) {
  const client = new ccc.ClientPublicMainnet({ url: CLOSED_PORT });
  const cells = sheet.transaction.inputs.map(({ previous_output: op }) => {
    const prev = sheet.context[op.tx_hash];
    const out = prev.outputs[Number(op.index)];
    return ccc.Cell.from({
      outPoint: { txHash: op.tx_hash, index: op.index },
      cellOutput: {
        capacity: out.capacity,
        lock: scriptOf(out.lock),
        type: out.type ? scriptOf(out.type) : undefined,
      },
      outputData: prev.outputs_data[Number(op.index)],
    });
  });
  await client.cache.recordCells(cells);
  return client;
}

async function messages(
  sheet: Sheet,
  groups: Group[],
): Promise<Map<string, string>> {
  const client = await clientFor(sheet);
  const tx = JsonRpcTransformers.transactionTo(
    sheet.transaction as unknown as Parameters<
      typeof JsonRpcTransformers.transactionTo
    >[0],
  );
  const out = new Map<string, string>();
  for (const g of groups) {
    if (g.kind === "carried") {
      continue;
    }
    const lock = lockOf(sheet, g.inputs[0]);
    if (g.kind === "single-key") {
      // As CCC's own single-key signer does (SignerCkbPublicKey.prepareTransaction): the lock is first set to
      // 65 zero bytes, then the sign hash is taken.
      const prepared = tx.clone();
      await prepared.prepareSighashAllWitness(scriptOf(lock), 65, client);
      const info = await prepared.getSignHashInfo(scriptOf(lock), client);
      if (info) out.set(g.lock_hash, info.message);
      continue;
    }
    const config = sheet.multisig_configs[lock.args.slice(0, 42)];
    const argsBytes = ccc.bytesFrom(lock.args);
    const since =
      argsBytes.length === 28
        ? ccc.numLeFromBytes(argsBytes.slice(20))
        : undefined;
    const signer = new ccc.SignerMultisigCkbReadonly(
      client,
      {
        publicKeyHashes: config.public_key_hashes,
        threshold: config.threshold,
        mustMatch: config.require_first_n,
      },
      {
        since,
        scriptInfos: [
          {
            codeHash: lock.code_hash,
            hashType: lock.hash_type as ccc.HashType,
            cellDeps: [],
          },
        ],
      },
    );
    const derived = (await signer.scriptInfos)[0].script;
    if (derived.args !== lock.args)
      problems.push(
        `${g.lock_hash}: CCC derives args ${derived.args}, the lock has ${lock.args}`,
      );
    const info = await signer.getSignInfo(tx, scriptOf(lock));
    if (info) out.set(g.lock_hash, info.message);
  }
  return out;
}

function members(sheet: Sheet, g: Group): string[] {
  const lock = lockOf(sheet, g.inputs[0]);
  return g.kind === "single-key"
    ? [lock.args]
    : sheet.multisig_configs[lock.args.slice(0, 42)].public_key_hashes;
}

function checkGroups(name: string, sheet: Sheet, groups: Group[]) {
  const found = new Map<string, number[]>();
  sheet.transaction.inputs.forEach((_, i) => {
    const h = scriptOf(lockOf(sheet, i)).hash();
    found.set(h, [...(found.get(h) ?? []), i]);
  });
  const want = groups.map((g) => `${g.lock_hash}:${g.inputs.join(",")}`).sort();
  const got = [...found].map(([h, idx]) => `${h}:${idx.join(",")}`).sort();
  if (want.join(" ") !== got.join(" "))
    problems.push(`${name}: the lock groups differ from expected.json`);
}

function checkSignatures(
  name: string,
  sheet: Sheet,
  groups: Group[],
  msgs: Map<string, string>,
  dropped: Set<string>,
) {
  for (const [gh, entries] of Object.entries(sheet.signatures)) {
    const g = groups.find((x) => x.lock_hash === gh);
    for (const [signer, sig] of Object.entries(entries)) {
      const key = `${gh}:${signer}`;
      if (!g) {
        if (!dropped.has(key))
          problems.push(`${name}: ${key} is under no group but isn't dropped`);
        continue;
      }
      if (g.kind === "carried") continue;
      let ok = members(sheet, g).includes(signer);
      if (ok) {
        try {
          ok =
            blake160(ccc.recoverMessageSecp256k1(msgs.get(gh)!, sig)) ===
            signer;
        } catch {
          ok = false;
        }
      }
      checkedSignatures += 1;
      if (ok === dropped.has(key))
        problems.push(
          `${name}: ${key} ${ok ? "verifies but is dropped" : "fails but is kept"}`,
        );
    }
  }
}

async function checkVector(dir: string) {
  const name = path.basename(dir);
  const expected = read<Expected>(path.join(dir, "expected.json"));
  if (expected.outcome !== "accepted" || !expected.messages || !expected.shown)
    return;
  const groups = expected.shown.groups;
  const main = ["attack.json", "merged.json"]
    .map((f) => path.join(dir, f))
    .find((f) => fs.existsSync(f))!;
  const sheet = read<Sheet>(main);
  checkGroups(name, sheet, groups);
  const msgs = await messages(sheet, groups);
  for (const [gh, msg] of Object.entries(expected.messages)) {
    checkedMessages += 1;
    if (msgs.get(gh) !== msg)
      problems.push(
        `${name}: ${gh}'s message is ${msgs.get(gh)} through CCC, ${msg} in expected.json`,
      );
  }
  const dropped = new Set(
    (expected.dropped ?? []).map((d) => `${d.group}:${d.signer}`),
  );
  checkSignatures(name, sheet, groups, msgs, dropped);
  const partials = path.join(dir, "partial");
  if (fs.existsSync(partials)) {
    for (const f of fs.readdirSync(partials).sort())
      checkSignatures(
        `${name}/${f}`,
        read<Sheet>(path.join(partials, f)),
        groups,
        msgs,
        new Set(),
      );
  }
}

function vectorFolders(root: string): string[] {
  if (fs.existsSync(path.join(root, "expected.json"))) return [root];
  return fs
    .readdirSync(root, { withFileTypes: true })
    .filter(
      (d) => d.isDirectory() && !d.name.startsWith(".") && d.name !== "partial",
    )
    .flatMap((d) => vectorFolders(path.join(root, d.name)))
    .sort();
}

const folders = process.argv.slice(2).flatMap(vectorFolders);
for (const dir of folders) await checkVector(dir);
for (const p of problems) console.log(p);
console.log(
  `ccc: ${folders.length} vectors, ${checkedMessages} messages, ${checkedSignatures} signatures, ${problems.length} problems`,
);
process.exit(problems.length ? 1 : 0);
