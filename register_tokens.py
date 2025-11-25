# register_tokens.py
from web3 import Web3
import json
import pandas as pd
from eth_account import Account
import time

def load_private_key():
    with open("sk.txt", "r") as f:
        priv_key = f.read().strip()
    if not priv_key.startswith("0x"):
        priv_key = "0x" + priv_key
    return priv_key

def register_tokens():
    priv_key = load_private_key()
    account = Account.from_key(priv_key)
    
    print(f"🔑 Using warden address: {account.address}")
    
    # Load contract info
    with open('contract_info.json', 'r') as f:
        contracts = json.load(f)
    
    # Load tokens
    tokens_df = pd.read_csv('erc20s.csv')
    
    # Connect to chains
    w3_avax = Web3(Web3.HTTPProvider("https://api.avax-test.network/ext/bc/C/rpc"))
    w3_bsc = Web3(Web3.HTTPProvider("https://data-seed-prebsc-1-s1.binance.org:8545/"))
    
    # Contract instances
    source_contract = w3_avax.eth.contract(
        address=contracts['source']['address'],
        abi=contracts['source']['abi']
    )
    
    destination_contract = w3_bsc.eth.contract(
        address=contracts['destination']['address'],
        abi=contracts['destination']['abi']
    )
    
    print("🚀 Starting token registration...")
    
    # Register tokens on Source (AVAX)
    avax_tokens = tokens_df[tokens_df['chain'] == 'avax']
    print(f"📝 Registering {len(avax_tokens)} tokens on AVAX...")
    
    for _, token in avax_tokens.iterrows():
        try:
            # Build transaction
            nonce = w3_avax.eth.get_transaction_count(account.address)
            tx = source_contract.functions.registerToken(token['address']).build_transaction({
                'chainId': w3_avax.eth.chain_id,
                'gas': 200000,
                'gasPrice': w3_avax.eth.gas_price,
                'nonce': nonce,
            })
            
            # Sign and send
            signed = w3_avax.eth.account.sign_transaction(tx, priv_key)
            tx_hash = w3_avax.eth.send_raw_transaction(signed.rawTransaction)
            receipt = w3_avax.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status == 1:
                print(f"✅ Registered token {token['address']} on AVAX")
            else:
                print(f"❌ Failed to register {token['address']} on AVAX")
                
        except Exception as e:
            print(f"❌ Error registering {token['address']} on AVAX: {e}")
    
    print("⏳ Waiting before BSC registration...")
    time.sleep(5)
    
    # Create wrapped tokens on Destination (BSC)
    bsc_tokens = tokens_df[tokens_df['chain'] == 'bsc']
    print(f"📝 Creating {len(bsc_tokens)} wrapped tokens on BSC...")
    
    for _, token in bsc_tokens.iterrows():
        try:
            # Build transaction
            nonce = w3_bsc.eth.get_transaction_count(account.address)
            tx = destination_contract.functions.createToken(
                token['address'],  # underlying_token
                "Wrapped Token",   # name
                "WTK"              # symbol
            ).build_transaction({
                'chainId': w3_bsc.eth.chain_id,
                'gas': 2500000,
                'gasPrice': w3_bsc.eth.gas_price,
                'nonce': nonce,
            })
            
            # Sign and send
            signed = w3_bsc.eth.account.sign_transaction(tx, priv_key)
            tx_hash = w3_bsc.eth.send_raw_transaction(signed.rawTransaction)
            receipt = w3_bsc.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status == 1:
                print(f"✅ Created wrapped token for {token['address']} on BSC")
            else:
                print(f"❌ Failed to create wrapped token for {token['address']} on BSC")
                
        except Exception as e:
            print(f"❌ Error creating wrapped token for {token['address']} on BSC: {e}")
    
    print("🎉 Token registration completed!")

if __name__ == "__main__":
    register_tokens()