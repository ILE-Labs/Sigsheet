// ckb-cli v2.0.0's `build_signature`, copied verbatim so the check runs exactly ckb-cli's own message code.
//
// Source: https://github.com/nervosnetwork/ckb-cli/blob/80efc21c30e9fc7847407a217034681b6e46c763/src/utils/tx_helper.rs#L507-L566
// ckb-cli is under the MIT license; NOTICE.md in this folder gives its copyright notice and full text. The `use`
// lines name what the function needs from ckb-cli's own imports (lines 1-17 of the same file); the function is
// unchanged.
#![allow(clippy::all)]
use ckb_hash::new_blake2b;
use ckb_jsonrpc_types as rpc_types;
use ckb_sdk::constants::SECP_SIGNATURE_SIZE;
use ckb_sdk::unlock::MultisigConfig;
use ckb_types::{
    bytes::{Bytes, BytesMut},
    core::TransactionView,
    packed::{self, WitnessArgs},
    prelude::*,
    H256,
};

pub fn build_signature<
    S: FnMut(&H256, &rpc_types::Transaction) -> Result<[u8; SECP_SIGNATURE_SIZE], String>,
>(
    tx: &TransactionView,
    input_size: usize,
    input_group_idxs: &[usize],
    witnesses: &[packed::Bytes],
    multisig_config_opt: Option<&MultisigConfig>,
    mut signer: S,
) -> Result<Bytes, String> {
    let init_witness_idx = input_group_idxs[0];
    let init_witness = if witnesses[init_witness_idx].raw_data().is_empty() {
        WitnessArgs::default()
    } else {
        WitnessArgs::from_slice(witnesses[init_witness_idx].raw_data().as_ref())
            .map_err(|err| err.to_string())?
    };

    let init_witness = if let Some(multisig_config) = multisig_config_opt {
        let lock_without_sig = {
            let sig_len = (multisig_config.threshold() as usize) * SECP_SIGNATURE_SIZE;
            let mut data = BytesMut::from(&multisig_config.to_witness_data()[..]);
            data.extend_from_slice(vec![0u8; sig_len].as_slice());
            data.freeze()
        };
        init_witness
            .as_builder()
            .lock(Some(lock_without_sig).pack())
            .build()
    } else {
        init_witness
            .as_builder()
            .lock(Some(Bytes::from(vec![0u8; SECP_SIGNATURE_SIZE])).pack())
            .build()
    };

    let mut blake2b = new_blake2b();
    blake2b.update(tx.hash().as_slice());
    blake2b.update(&(init_witness.as_bytes().len() as u64).to_le_bytes());
    blake2b.update(&init_witness.as_bytes());
    for idx in input_group_idxs.iter().skip(1).cloned() {
        let other_witness: &packed::Bytes = &witnesses[idx];
        blake2b.update(&(other_witness.len() as u64).to_le_bytes());
        blake2b.update(&other_witness.raw_data());
    }
    for outter_witness in &witnesses[input_size..witnesses.len()] {
        blake2b.update(&(outter_witness.len() as u64).to_le_bytes());
        blake2b.update(&outter_witness.raw_data());
    }
    let mut message = [0u8; 32];
    blake2b.finalize(&mut message);
    let message = H256::from(message);
    let mut new_witnesses = witnesses.to_vec();
    new_witnesses[init_witness_idx] = init_witness.as_bytes().pack();
    let new_tx = tx
        .as_advanced_builder()
        .set_witnesses(new_witnesses)
        .build();
    signer(&message, &new_tx.data().into()).map(|data| Bytes::from(data.to_vec()))
}
