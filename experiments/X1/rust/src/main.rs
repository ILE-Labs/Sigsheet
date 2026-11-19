//! X1 Rust paths: print the signing message of every lock group in a case, as computed by
//!   (a) ckb-cli v2.0.0's build_signature (copied verbatim in ckb_cli_tx_helper.rs), and
//!   (b) ckb-sdk 5.0.0's script signers (SecpSighashScriptSigner, SecpMultisigScriptSigner),
//!       called from the crate with a signer that records the message it is asked to sign.
//!
//! Usage: x1-rust-paths <case.json>
//! The case file holds "tx" (a transaction in the CKB RPC JSON form) and "groups": one entry per
//! lock group with "name", "kind" ("multisig" or "sighash"), "lock" (the lock script, RPC JSON),
//! "input_indices", and for multisig "deployment" and "multisig": {"require_first_n", "threshold",
//! "key_hashes"}.
//! Output: one JSON object per line: {"group", "path", "message"} or {"group", "path", "error"}.
mod ckb_cli_tx_helper;

use ckb_jsonrpc_types as rpc_types;
use ckb_sdk::constants::MultisigScript;
use ckb_sdk::traits::{Signer, SignerError};
use ckb_sdk::types::{ScriptGroup, ScriptGroupType};
use ckb_sdk::unlock::{MultisigConfig, ScriptSigner, SecpMultisigScriptSigner, SecpSighashScriptSigner};
use ckb_types::{bytes::Bytes, core::TransactionView, packed, prelude::IntoTransactionView, H160};
use serde_json::{json, Value};
use std::sync::{Arc, Mutex};

struct Capture {
    ids: Vec<Vec<u8>>,
    messages: Arc<Mutex<Vec<Vec<u8>>>>,
}

impl Signer for Capture {
    fn match_id(&self, id: &[u8]) -> bool {
        self.ids.iter().any(|x| x.as_slice() == id)
    }
    fn sign(&self, _id: &[u8], message: &[u8], _recoverable: bool, _tx: &TransactionView)
        -> Result<Bytes, SignerError> {
        self.messages.lock().unwrap().push(message.to_vec());
        Ok(Bytes::from(vec![0x11u8; 65]))
    }
}

fn hex(b: &[u8]) -> String {
    format!("0x{}", b.iter().map(|x| format!("{:02x}", x)).collect::<String>())
}

fn unhex(s: &str) -> Vec<u8> {
    let s = s.trim_start_matches("0x");
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap()).collect()
}

fn report(group: &str, path: &str, r: Result<Vec<u8>, String>) {
    match r {
        Ok(m) => println!("{}", json!({"group": group, "path": path, "message": hex(&m)})),
        Err(e) => println!("{}", json!({"group": group, "path": path, "error": e})),
    }
}

fn main() {
    let path = std::env::args().nth(1).expect("usage: x1-rust-paths <case.json>");
    let case: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    let rpc_tx: rpc_types::Transaction = serde_json::from_value(case["tx"].clone()).unwrap();
    let tx: packed::Transaction = rpc_tx.into();
    let tx = tx.into_view();

    for g in case["groups"].as_array().unwrap() {
        let name = g["name"].as_str().unwrap();
        let idxs: Vec<usize> = g["input_indices"].as_array().unwrap().iter()
            .map(|v| v.as_u64().unwrap() as usize).collect();
        let lock_script: packed::Script =
            serde_json::from_value::<rpc_types::Script>(g["lock"].clone()).unwrap().into();
        let group = ScriptGroup {
            script: lock_script,
            group_type: ScriptGroupType::Lock,
            input_indices: idxs.clone(),
            output_indices: vec![],
        };
        let config = if g["kind"].as_str() == Some("multisig") {
            let m = &g["multisig"];
            let keys: Vec<H160> = m["key_hashes"].as_array().unwrap().iter()
                .map(|k| H160::from_slice(&unhex(k.as_str().unwrap())).unwrap()).collect();
            // The code hash doesn't enter the message. MultisigScript has only Legacy and V2, so the
            // 2024 deployment is given as Legacy: to_witness_data() and threshold() don't change.
            let script = if g["deployment"].as_str() == Some("v2") { MultisigScript::V2 } else { MultisigScript::Legacy };
            Some(MultisigConfig::new_with(script, keys,
                m["require_first_n"].as_u64().unwrap() as u8,
                m["threshold"].as_u64().unwrap() as u8).unwrap())
        } else {
            None
        };

        // (a) ckb-cli v2.0.0 build_signature, with the witnesses TxHelper::sign_inputs passes.
        let witnesses = ckb_cli_tx_helper::init_witnesses(&tx);
        let mut seen: Option<Vec<u8>> = None;
        let res = ckb_cli_tx_helper::build_signature(&tx, tx.inputs().len(), &idxs, &witnesses,
            config.as_ref(), |message, _tx| { seen = Some(message.as_bytes().to_vec()); Ok([0u8; 65]) });
        report(name, "ckb-cli v2.0.0 build_signature",
               res.and_then(|_| seen.ok_or_else(|| "no message".to_string())));

        // (b) ckb-sdk 5.0.0 script signer, through the crate's own ScriptSigner::sign_tx.
        let messages = Arc::new(Mutex::new(vec![]));
        let ids: Vec<Vec<u8>> = match &config {
            Some(c) => c.sighash_addresses().iter().map(|h| h.as_bytes().to_vec()).collect(),
            None => vec![unhex(g["lock"]["args"].as_str().unwrap())],
        };
        let cap = Box::new(Capture { ids, messages: messages.clone() });
        let signed = match config {
            Some(c) => SecpMultisigScriptSigner::new(cap, c).sign_tx(&tx, &group),
            None => SecpSighashScriptSigner::new(cap).sign_tx(&tx, &group),
        };
        let first = messages.lock().unwrap().first().cloned();
        report(name, "ckb-sdk 5.0.0 ScriptSigner::sign_tx", match (signed, first) {
            (Ok(_), Some(m)) => Ok(m),
            (Err(e), Some(m)) => Err(format!("message {} computed, then sign_tx failed: {}", hex(&m), e)),
            (Err(e), None) => Err(e.to_string()),
            (Ok(_), None) => Err("no message".to_string()),
        });
    }
}
