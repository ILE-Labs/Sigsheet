//! The independent check of the vectors' messages with ckb-cli's and ckb-sdk's own code.
//!
//! For every vector whose `expected.json` lists messages, from the vector's own files (never the generator's code),
//! each lock group's message is computed two ways, and each must equal `expected.json`'s:
//! - ckb-cli v2.0.0's `build_signature` (copied verbatim in `ckb_cli_build_signature.rs`), given the witnesses its
//!   `TxHelper::init_witnesses` passes;
//! - ckb-sdk 5.0.0's own script signers (`SecpMultisigScriptSigner`, `SecpSighashScriptSigner`) through
//!   `ScriptSigner::sign_tx`, with a signer that records the message it is asked to sign.
//!
//! Each group is found again from the file's context and must match `expected.json`'s lock hash and inputs.
//!
//! Usage: check-ckb-sdk <vector folder>...

mod ckb_cli_build_signature;

use ckb_jsonrpc_types as rpc_types;
use ckb_sdk::constants::MultisigScript;
use ckb_sdk::traits::{Signer, SignerError};
use ckb_sdk::types::{ScriptGroup, ScriptGroupType};
use ckb_sdk::unlock::{
    MultisigConfig, ScriptSigner, SecpMultisigScriptSigner, SecpSighashScriptSigner,
};
use ckb_types::{bytes::Bytes, core::TransactionView, packed, prelude::*, H160};
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

/// A signer that records each message it is asked to sign and returns 65 bytes of filler.
struct Capture {
    ids: Vec<Vec<u8>>,
    messages: Arc<Mutex<Vec<Vec<u8>>>>,
}

impl Signer for Capture {
    fn match_id(&self, id: &[u8]) -> bool {
        self.ids.iter().any(|x| x.as_slice() == id)
    }

    fn sign(
        &self,
        _id: &[u8],
        message: &[u8],
        _recoverable: bool,
        _tx: &TransactionView,
    ) -> Result<Bytes, SignerError> {
        self.messages.lock().unwrap().push(message.to_vec());
        Ok(Bytes::from(vec![0u8; 65]))
    }
}

fn hex(b: &[u8]) -> String {
    format!(
        "0x{}",
        b.iter().map(|x| format!("{:02x}", x)).collect::<String>()
    )
}

fn unhex(s: &str) -> Vec<u8> {
    let s = s.trim_start_matches("0x");
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap())
        .collect()
}

fn read(path: &Path) -> Value {
    serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap()
}

/// The witnesses ckb-cli's `TxHelper::init_witnesses` passes to `build_signature`: the transaction's own, padded with
/// empty ones to the number of inputs (tx_helper.rs L218-L224 at the same commit).
fn init_witnesses(tx: &TransactionView) -> Vec<packed::Bytes> {
    let mut witnesses: Vec<packed::Bytes> = tx.witnesses().into_iter().collect();
    while witnesses.len() < tx.inputs().len() {
        witnesses.push(Bytes::new().pack());
    }
    witnesses
}

fn lock_of(sheet: &Value, input: usize) -> packed::Script {
    let op = &sheet["transaction"]["inputs"][input]["previous_output"];
    let prev = &sheet["context"][op["tx_hash"].as_str().unwrap()];
    let index =
        usize::from_str_radix(op["index"].as_str().unwrap().trim_start_matches("0x"), 16).unwrap();
    let lock: rpc_types::Script =
        serde_json::from_value(prev["outputs"][index]["lock"].clone()).unwrap();
    lock.into()
}

fn multisig_config(sheet: &Value, kind: &str, lock: &packed::Script) -> MultisigConfig {
    let args: Bytes = lock.args().unpack();
    let config = &sheet["multisig_configs"][hex(&args[..20])];
    let keys: Vec<H160> = config["public_key_hashes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|k| H160::from_slice(&unhex(k.as_str().unwrap())).unwrap())
        .collect();
    // The code hash doesn't enter the message; MultisigScript only picks the deployment's code hash.
    let script = if kind == "multisig-v2" {
        MultisigScript::V2
    } else {
        MultisigScript::Legacy
    };
    let r = config["require_first_n"].as_u64().unwrap() as u8;
    let m = config["threshold"].as_u64().unwrap() as u8;
    MultisigConfig::new_with(script, keys, r, m).unwrap()
}

fn ckb_cli_message(
    tx: &TransactionView,
    inputs: &[usize],
    config: Option<&MultisigConfig>,
) -> Result<Vec<u8>, String> {
    let witnesses = init_witnesses(tx);
    let mut seen = None;
    ckb_cli_build_signature::build_signature(
        tx,
        tx.inputs().len(),
        inputs,
        &witnesses,
        config,
        |message, _tx| {
            seen = Some(message.as_bytes().to_vec());
            Ok([0u8; 65])
        },
    )?;
    seen.ok_or_else(|| "no message".to_string())
}

fn ckb_sdk_message(
    tx: &TransactionView,
    group: &ScriptGroup,
    config: Option<MultisigConfig>,
) -> Result<Vec<u8>, String> {
    let messages = Arc::new(Mutex::new(vec![]));
    let ids: Vec<Vec<u8>> = match &config {
        Some(c) => c
            .sighash_addresses()
            .iter()
            .map(|h| h.as_bytes().to_vec())
            .collect(),
        None => vec![group.script.args().raw_data().to_vec()],
    };
    let capture = Box::new(Capture {
        ids,
        messages: messages.clone(),
    });
    let signed = match config {
        Some(c) => SecpMultisigScriptSigner::new(capture, c).sign_tx(tx, group),
        None => SecpSighashScriptSigner::new(capture).sign_tx(tx, group),
    };
    signed.map_err(|e| e.to_string())?;
    let first = messages.lock().unwrap().first().cloned();
    first.ok_or_else(|| "no message".to_string())
}

fn check_vector(dir: &Path, problems: &mut Vec<String>) -> usize {
    let expected = read(&dir.join("expected.json"));
    if expected["outcome"] != "accepted"
        || !expected["messages"].is_object()
        || !expected["shown"].is_object()
    {
        return 0;
    }
    let name = dir.file_name().unwrap().to_string_lossy().to_string();
    let attack = dir.join("attack.json");
    let file = if attack.exists() {
        attack
    } else {
        dir.join("merged.json")
    };
    let sheet = read(&file);
    let rpc_tx: rpc_types::Transaction =
        serde_json::from_value(sheet["transaction"].clone()).unwrap();
    let tx: packed::Transaction = rpc_tx.into();
    let tx = tx.into_view();
    let mut checked = 0;
    for g in expected["shown"]["groups"].as_array().unwrap() {
        let kind = g["kind"].as_str().unwrap();
        if kind == "carried" {
            continue;
        }
        let inputs: Vec<usize> = g["inputs"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_u64().unwrap() as usize)
            .collect();
        let lock = lock_of(&sheet, inputs[0]);
        let lock_hash = g["lock_hash"].as_str().unwrap();
        let found: Vec<usize> = (0..tx.inputs().len())
            .filter(|&i| lock_of(&sheet, i) == lock)
            .collect();
        if hex(lock.calc_script_hash().as_slice()) != lock_hash || found != inputs {
            problems.push(format!(
                "{name}: group {lock_hash} differs from the file's inputs"
            ));
            continue;
        }
        let config = if kind == "single-key" {
            None
        } else {
            Some(multisig_config(&sheet, kind, &lock))
        };
        let group = ScriptGroup {
            script: lock,
            group_type: ScriptGroupType::Lock,
            input_indices: inputs.clone(),
            output_indices: vec![],
        };
        let want = expected["messages"][lock_hash].as_str().unwrap();
        for (path, got) in [
            (
                "ckb-cli build_signature",
                ckb_cli_message(&tx, &inputs, config.as_ref()),
            ),
            (
                "ckb-sdk ScriptSigner::sign_tx",
                ckb_sdk_message(&tx, &group, config),
            ),
        ] {
            checked += 1;
            match got {
                Ok(m) if hex(&m) == want => {}
                Ok(m) => problems.push(format!(
                    "{name}: {lock_hash}: {path} gives {}, expected.json {want}",
                    hex(&m)
                )),
                Err(e) => problems.push(format!("{name}: {lock_hash}: {path} failed: {e}")),
            }
        }
    }
    checked
}

fn vector_folders(root: &Path, out: &mut Vec<PathBuf>) {
    if root.join("expected.json").exists() {
        out.push(root.to_path_buf());
        return;
    }
    let mut entries: Vec<PathBuf> = std::fs::read_dir(root)
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.is_dir() && !p.file_name().unwrap().to_string_lossy().starts_with('.'))
        .filter(|p| p.file_name().unwrap() != "partial")
        .collect();
    entries.sort();
    for e in entries {
        vector_folders(&e, out);
    }
}

fn main() {
    let mut folders = vec![];
    for root in std::env::args().skip(1) {
        vector_folders(Path::new(&root), &mut folders);
    }
    let mut problems = vec![];
    let mut checked = 0;
    for dir in &folders {
        checked += check_vector(dir, &mut problems);
    }
    for p in &problems {
        println!("{p}");
    }
    println!(
        "ckb-sdk: {} vectors, {} messages, {} problems",
        folders.len(),
        checked,
        problems.len()
    );
    std::process::exit(if problems.is_empty() { 0 } else { 1 });
}
