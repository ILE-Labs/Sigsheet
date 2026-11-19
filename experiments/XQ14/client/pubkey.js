// XQ14: read the emulator's public key at Neuron's default receiving path, with Neuron's host library.
const SpeculosTransport = require("@ledgerhq/hw-transport-node-speculos").default;
const LedgerCKB = require("@magickbase/hw-app-ckb").default;
(async () => {
  const transport = await SpeculosTransport.open({ apduPort: 9999 });
  const ckb = new LedgerCKB(transport);
  const conf = await ckb.getAppConfiguration();
  const path = process.argv[2] || "44'/309'/0'/0/0";
  const pk = await ckb.getWalletPublicKey(path, true);
  console.log(JSON.stringify({ app: conf, path, ...pk }, null, 1));
  await transport.close();
})().catch((e) => { console.error("ERROR", e.message || e); process.exit(1); });
