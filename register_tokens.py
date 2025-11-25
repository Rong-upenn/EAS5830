# register_tokens.py
from web3 import Web3
import json
import csv
from eth_account import Account
import time

def load_private_key():
    """Load private key from sk.txt"""
    with open("sk.txt", "r") as f:
        priv_key = f.read().strip()
    if not priv_key.startswith("0x"):
        priv_key = "0x" + priv_key
    return priv_key

def load_tokens_from_csv():
    """Load tokens from erc20s.csv without pandas"""
    tokens = []
    try:
        with open('erc20s.csv', 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                tokens.append(row)
        print(f"📝 Found {len(tokens)} tokens in erc20s.csv")
        for token in tokens:
            print(f"   {token['chain']}: {token['address']}")
        return tokens
    except Exception as e:
        print(f"❌ Error reading erc20s.csv: {e}")
        return []

def sign_and_send_transaction(w3, contract, function_name, args, private_key, nonce, gas_limit=300000):
    """Helper function to sign and send transactions"""
    try:
        account = Account.from_key(private_key)
        
        transaction = getattr(contract.functions, function_name)(*args).build_transaction({
            'chainId': w3.eth.chain_id,
            'gas': gas_limit,
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
        })
        
        # Sign transaction
        signed_txn = w3.eth.account.sign_transaction(transaction, private_key)
        
        # Try both attribute names for compatibility
        if hasattr(signed_txn, 'rawTransaction'):
            raw_tx = signed_txn.rawTransaction
        else:
            raw_tx = signed_txn.raw_transaction
            
        # Send transaction
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        print(f"📤 Transaction sent: {tx_hash.hex()}")
        
        # Wait for receipt
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status == 1:
            print(f"✅ Transaction successful in block {receipt.blockNumber}")
            return True
        else:
            print(f"❌ Transaction failed")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def register_tokens():
    # Load private key
    priv_key = load_private_key()
    account = Account.from_key(priv_key)
    
    print(f"🔑 Using warden address: {account.address}")
    
    # Load contract info
    with open('contract_info.json', 'r') as f:
        contracts = json.load(f)
    
    # Load tokens from erc20s.csv
    tokens = load_tokens_from_csv()
    if not tokens:
        return
    
    # Connect to chains
    w3_avax = Web3(Web3.HTTPProvider("https://api.avax-test.network/ext/bc/C/rpc"))
    w3_bsc = Web3(Web3.HTTPProvider("https://data-seed-prebsc-1-s1.binance.org:8545/"))
    
    print(f"✅ AVAX connected: {w3_avax.is_connected()}")
    print(f"✅ BSC connected: {w3_bsc.is_connected()}")
    
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
    avax_tokens = [t for t in tokens if t['chain'] == 'avax']
    print(f"📝 Registering {len(avax_tokens)} tokens on AVAX...")
    
    # Get initial nonce for AVAX
    avax_nonce = w3_avax.eth.get_transaction_count(account.address)
    
    for token in avax_tokens:
        try:
            print(f"\n🔄 Registering token {token['address']} on AVAX...")
            
            # Use the helper function with proper nonce handling
            success = sign_and_send_transaction(
                w3_avax,
                source_contract,
                'registerToken',
                [token['address']],
                priv_key,
                avax_nonce,
                200000
            )
            
            if success:
                print(f"✅ Successfully registered token {token['address']} on AVAX")
                avax_nonce += 1  # Increment nonce for next transaction
            else:
                print(f"❌ Failed to register {token['address']} on AVAX")
                
        except Exception as e:
            print(f"❌ Error registering {token['address']} on AVAX: {e}")
            # If failed, get fresh nonce
            avax_nonce = w3_avax.eth.get_transaction_count(account.address)
    
    print("⏳ Waiting before BSC registration...")
    time.sleep(10)  # Longer wait to ensure all transactions are processed
    
    # Create wrapped tokens on Destination (BSC)
    bsc_tokens = [t for t in tokens if t['chain'] == 'bsc']
    print(f"📝 Creating {len(bsc_tokens)} wrapped tokens on BSC...")
    
    # Get fresh nonce for BSC
    bsc_nonce = w3_bsc.eth.get_transaction_count(account.address)
    
    for token in bsc_tokens:
        try:
            print(f"\n🔄 Creating wrapped token for {token['address']} on BSC...")
            
            # Use the helper function with proper nonce handling
            success = sign_and_send_transaction(
                w3_bsc,
                destination_contract,
                'createToken',
                [token['address'], "Wrapped Token", "WTK"],
                priv_key,
                bsc_nonce,
                2500000
            )
            
            if success:
                print(f"✅ Successfully created wrapped token for {token['address']} on BSC")
                bsc_nonce += 1  # Increment nonce for next transaction
            else:
                print(f"❌ Failed to create wrapped token for {token['address']} on BSC")
                
        except Exception as e:
            print(f"❌ Error creating wrapped token for {token['address']} on BSC: {e}")
            # If failed, get fresh nonce
            bsc_nonce = w3_bsc.eth.get_transaction_count(account.address)
    
    print("\n🎉 Token registration completed!")
    print("✅ Your bridge is now ready to use!")

if __name__ == "__main__":
    register_tokens()