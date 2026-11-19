// XQ14: sign one job on the emulated Ledger with Neuron's host library, pressing the buttons through Speculos's
// REST API and recording every screen the device shows.
//
// Usage: node sign.js <job.json> <out.json> [--reject]
// job.json: {"kind": "transaction", "signPath", "changePath", "rawTx", "witnesses", "context"}  (the arguments
//           Neuron's ledger.ts passes to ledgerCKB.signTransaction), or
//           {"kind": "message_hash", "signPath", "hash"} (INS_SIGN_MESSAGE_HASH, 0x07).
// The approval rule: press right until the screen says "Accept" (or "Reject" with --reject), then press both.
const fs = require("fs");
const crypto = require("crypto");
const SpeculosTransport = require("@ledgerhq/hw-transport-node-speculos").default;
const LedgerCKB = require("@magickbase/hw-app-ckb").default;
const blockchain = require("@magickbase/hw-app-ckb/lib/annotated");

const API = "http://127.0.0.1:5000";

async function screen() {
  const r = await fetch(`${API}/events?currentscreenonly=true`);
  const j = await r.json();
  return j.events.map((e) => e.text).join(" | ");
}

async function press(button) {
  await fetch(`${API}/button/${button}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "press-and-release" }),
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function approve(rec, target, done) {
  // Phase 1: wait until the device leaves its idle screen ("Nervos | 0.6.3") or the request ends.
  const idle = (s) => s.startsWith("Nervos");
  let s = await screen();
  while (!done.v && (s === "" || idle(s))) { await sleep(100); s = await screen(); }
  if (done.v) return;
  // Phase 2: record each screen, press right until the target, then press both.
  for (let step = 0; step < 400 && !done.v; step++) {
    s = await screen();
    rec.screens.push(s);
    if (s.includes(target)) { await press("both"); rec.presses.both++; return; }
    await press("right"); rec.presses.right++;
    // wait for the screen to change before reading it again
    for (let t = 0; t < 40; t++) { await sleep(50); if ((await screen()) !== s) break; }
  }
}

(async () => {
  const [jobFile, outFile] = process.argv.slice(2, 4);
  const reject = process.argv.includes("--reject");
  const job = JSON.parse(fs.readFileSync(jobFile, "utf8"));
  const transport = await SpeculosTransport.open({ apduPort: 9999 });
  const ckb = new LedgerCKB(transport);
  const rec = { job: jobFile, kind: job.kind, screens: [], presses: { right: 0, both: 0 } };
  // Wait for the idle screen before starting.
  for (let i = 0; i < 50 && !(await screen()).startsWith("Nervos"); i++) await sleep(100);
  const done = { v: false };
  const t0 = Date.now();
  let signing;
  if (job.kind === "transaction") {
    const annotated = ckb.buildAnnotatedTransaction(job.signPath, job.rawTx, job.witnesses, job.context, job.changePath);
    const bytes = Buffer.from(blockchain.SerializeAnnotatedTransaction(annotated));
    rec.annotated_bytes = bytes.length;
    rec.annotated_sha256 = crypto.createHash("sha256").update(bytes).digest("hex");
    rec.apdus = Math.ceil(bytes.length / 230);
    signing = ckb.signAnnotatedTransaction(annotated);
  } else if (job.kind === "message_hash") {
    const path = require("bip32-path").fromString(job.signPath).toPathArray();
    const rawPath = Buffer.alloc(1 + 4 * path.length);
    rawPath.writeUInt8(path.length, 0);
    path.forEach((c, i) => rawPath.writeUInt32BE(c, 1 + 4 * i));
    signing = (async () => {
      await transport.send(0x80, 0x07, 0x00, 0x00, rawPath);
      const resp = await transport.send(0x80, 0x07, 0x80, 0x00, Buffer.from(job.hash.replace(/^0x/, ""), "hex"));
      return resp.slice(0, 65).toString("hex");
    })();
  }
  const watcher = approve(rec, reject ? "Reject" : "Accept", done);
  try {
    rec.signature = await signing;
    rec.result = "signed";
  } catch (e) {
    rec.result = "error";
    rec.error = e.message || String(e);
    rec.status_code = e.statusCode !== undefined ? "0x" + e.statusCode.toString(16) : undefined;
  }
  done.v = true;
  await watcher.catch(() => {});
  rec.seconds = (Date.now() - t0) / 1000;
  await transport.close();
  fs.writeFileSync(outFile, JSON.stringify(rec, null, 1));
  console.log(JSON.stringify({ result: rec.result, error: rec.error, status: rec.status_code, screens: rec.screens.length,
                               presses: rec.presses, seconds: rec.seconds, annotated_bytes: rec.annotated_bytes }));
})().catch((e) => { console.error("ERROR", e); process.exit(1); });
