
from web3 import Web3
from web3.providers.rpc import HTTPProvider
import json
import os
from dotenv import load_dotenv

load_dotenv()

def deploy_contract(w3, contract_bytecode, contract_abi, constructor_args, private_key):
    account = Account.from_key(private_key)
    
    contract = w3.eth.contract(abi=contract_abi, bytecode=contract_bytecode)
    
    transaction = contract.constructor(*constructor_args).build_transaction({
        'chainId': w3.eth.chain_id,
        'gas': 2000000,
        'gasPrice': w3.eth.gas_price,
        'nonce': w3.eth.get_transaction_count(account.address),
    })
    
    signed_txn = w3.eth.account.sign_transaction(transaction, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
    
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt.contractAddress

# 使用你已经部署的合约地址更新 contract_info.json