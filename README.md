# Sigsheet

A shared file format for signing CKB multisig transactions.

A Sigsheet is one file per transaction. It carries the transaction, proof of every input, the multisig configuration and every signature collected so far. Each signer adds a signature with the wallet they already use, in any order. Anyone can merge copies of the file, and anyone can finalize the transaction once enough signatures are in. Nobody has to collect and forward the signatures.

## Goals

- **One format for the tools people already use:** ckb-cli, Neuron and CCC read and write the same file.
- **No collector:** signatures can be added and merged in any order, by anyone holding a copy.
- **Existing multisig:** it works with the multisig lock scripts and addresses already on chain. There's no new on-chain script.
- **Checkable before signing:** the file carries what a signer needs to verify the transaction, including proof of every input.

## Status

Early. The format's design is settled, and the specification and reference implementation are in progress. The planned versions are tracked as milestones in this repository.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).

Maintained by ILE Labs.
