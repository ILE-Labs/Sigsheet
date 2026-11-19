//! XC4 harness. Usage:
//!   xc4-idl-harness <locks.json> <idl files...> -- <code cell data files...>
//! For each IDL file: is it RFC 8785 canonical, does it parse, does `IdlDocument::validate` accept it,
//! and does `IdlClient::decode_lock_witness` decode each multisig witness lock from locks.json?
//! For each code cell data file: does `IdlClient::verify_commitment` find a Binding Trailer 1?
//! Prints one JSON object per line.
use ckb_idl_client::{IdlClient, IdlDocument};
use serde_json::json;
use std::fs;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let split = args.iter().position(|a| a == "--").unwrap_or(args.len());
    let locks: serde_json::Value = serde_json::from_slice(&fs::read(&args[0]).unwrap()).unwrap();
    let client = IdlClient::new();
    for idl_path in &args[1..split] {
        let bytes = fs::read(idl_path).unwrap();
        let value: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        let canonical = serde_json_canonicalizer::to_vec(&value).unwrap() == bytes;
        let doc: IdlDocument = match IdlClient::parse_document(&bytes) {
            Ok(d) => d,
            Err(e) => {
                println!("{}", json!({"idl": idl_path, "bytes": bytes.len(), "canonical": canonical,
                    "parse": format!("{}: {} ({})", e.category(), e, e.path())}));
                continue;
            }
        };
        let validate = match doc.validate() {
            Ok(_) => "ok".to_string(),
            Err(e) => format!("{} at '{}': {}", e.category(), e.path(), e),
        };
        println!("{}", json!({"idl": idl_path, "bytes": bytes.len(), "canonical": canonical, "parse": "ok", "validate": validate}));
        if validate != "ok" {
            continue;
        }
        for lock in locks.as_array().unwrap() {
            let raw = hex::decode(lock["lock"].as_str().unwrap().trim_start_matches("0x")).unwrap();
            let result = match client.decode_lock_witness(&doc, &raw) {
                Ok(obj) => format!("ok: {:?}", obj).chars().take(160).collect::<String>(),
                Err(e) => format!("{} at '{}': {}", e.category(), e.path(), e),
            };
            println!("{}", json!({"idl": idl_path, "case": lock["case"], "witness_index": lock["witness_index"],
                "config": format!("R={} M={} N={}", lock["R"], lock["M"], lock["N"]), "lock_bytes": raw.len(),
                "decode": result}));
        }
    }
    let any_idl = fs::read(&args[1]).unwrap();
    for data_path in args.iter().skip(split + 1) {
        let data = fs::read(data_path).unwrap();
        let tail = hex::encode(&data[data.len().saturating_sub(8)..]);
        let result = match IdlClient::verify_commitment(&any_idl, &data) {
            Ok(()) => "ok".to_string(),
            Err(e) => format!("{}: {}", e.category(), e),
        };
        println!("{}", json!({"code_cell_data": data_path, "bytes": data.len(), "last_8_bytes": tail,
            "trailer_magic_expected": "434b4249444c0000", "verify_commitment": result}));
    }
}
