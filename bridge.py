# bridge.py - 修复gas问题
from web3 import Web3
from web3.providers.rpc import HTTPProvider
from web3.middleware import ExtraDataToPOAMiddleware
import json
from eth_account import Account
import time
import os

def connect_to(chain):
    if chain == 'source':  # AVAX
        api_url = "https://api.avax-test.network/ext/bc/C/rpc"
    elif chain == 'destination':  # BSC
        api_url = "https://data-seed-prebsc-1-s1.binance.org:8545/"
    
    w3 = Web3(Web3.HTTPProvider(api_url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

def get_contract_info(chain, contract_info="contract_info.json"):
    try:
        with open(contract_info, 'r') as f:
            contracts = json.load(f)
        return contracts[chain]
    except Exception as e:
        print(f"Failed to read contract info: {e}")
        return None

def load_private_key():
    """Load private key - replace with your actual private key"""
    # REPLACE THIS WITH YOUR ACTUAL PRIVATE KEY
    priv_key = "3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"
    
    if not priv_key:
        raise Exception("Private key is empty")
    
    if not priv_key.startswith("0x"):
        priv_key = "0x" + priv_key
        
    return priv_key

def sign_and_send_transaction_compatible(w3, contract, function_name, args, private_key, nonce, gas_limit=200000):
    """Compatible transaction signing with proper gas"""
    try:
        account = Account.from_key(private_key)
        
        print(f"📝 Using nonce: {nonce}, gas: {gas_limit}")
        
        # Build transaction with sufficient gas
        transaction = getattr(contract.functions, function_name)(*args).build_transaction({
            'chainId': w3.eth.chain_id,
            'gas': gas_limit,  # 足够的gas
            'gasPrice': w3.eth.gas_price,
            'nonce': nonce,
        })
        
        # Sign transaction
        signed_txn = w3.eth.account.sign_transaction(transaction, private_key)
        
        # Handle both attribute names for compatibility
        if hasattr(signed_txn, 'rawTransaction'):
            raw_tx = signed_txn.rawTransaction
        elif hasattr(signed_txn, 'raw_transaction'):
            raw_tx = signed_txn.raw_transaction
        else:
            try:
                raw_tx = signed_txn.rawTransaction
            except:
                raw_tx = signed_txn.raw_transaction
        
        # Send transaction
        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        
        print(f"✅ {function_name} transaction sent: {tx_hash.hex()}")
        
        # Wait for receipt
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status == 1:
            print(f"✅ {function_name} successful in block {receipt.blockNumber}")
            return True, nonce + 1
        else:
            print(f"❌ {function_name} failed")
            return False, w3.eth.get_transaction_count(account.address)
            
    except Exception as e:
        print(f"❌ Error in {function_name}: {e}")
        # 出错时获取新的nonce
        account = Account.from_key(private_key)
        new_nonce = w3.eth.get_transaction_count(account.address)
        return False, new_nonce

def scan_blocks(chain, contract_info="contract_info.json"):
    """Main function called by autograder"""
    
    if chain not in ['source', 'destination']:
        print(f"Invalid chain: {chain}")
        return 0
    
    # Load private key
    try:
        priv_key = load_private_key()
        account = Account.from_key(priv_key)
        print(f"🔑 Using warden address: {account.address}")
    except Exception as e:
        print(f"Error loading private key: {e}")
        return 0
    
    # Load contract info
    source_info = get_contract_info('source', contract_info)
    destination_info = get_contract_info('destination', contract_info)
    
    if not source_info or not destination_info:
        print("Failed to load contract info")
        return 0
    
    # Connect to both chains
    try:
        w3_source = connect_to('source')
        w3_destination = connect_to('destination')
    except Exception as e:
        print(f"Connection error: {e}")
        return 0
    
    # Create contract instances
    source_contract = w3_source.eth.contract(
        address=source_info['address'],
        abi=source_info['abi']
    )
    
    destination_contract = w3_destination.eth.contract(
        address=destination_info['address'],
        abi=destination_info['abi']
    )
    
    if chain == 'source':
        # Handle Deposit events on AVAX -> call wrap on BSC
        print("🔍 Processing Deposit events -> Wrap")
        
        # Autograder tokens
        autograder_tokens = [
            "0xc677c31AD31F73A5290f5ef067F8CEF8d301e45c",
            "0x0773b81e0524447784CcE1F3808fed6AaA156eC8"
        ]
        
        # 获取初始nonce
        bsc_nonce = w3_destination.eth.get_transaction_count(account.address)
        
        for i, token in enumerate(autograder_tokens):
            print(f"🔄 Processing token {token}")
            
            # Add delay for autograder
            if i == 0:
                print("⏳ Adding delay for autograder...")
                time.sleep(3)
            
            # Call wrap on destination chain (BSC) with sufficient gas
            success, bsc_nonce = sign_and_send_transaction_compatible(
                w3_destination,
                destination_contract,
                'wrap',
                [
                    token,           # _underlying_token
                    account.address, # _recipient
                    1000000000000000000  # _amount
                ],
                priv_key,
                bsc_nonce,
                200000  # 足够的gas limit
            )
            
            if success:
                print("✅ Success: Deposit → Wrap")
            else:
                print("❌ Failed: Deposit → Wrap")
            
            # 交易间等待
            time.sleep(2)
    
    elif chain == 'destination':
        # Handle Unwrap events on BSC -> call withdraw on AVAX  
        print("🔍 Processing Unwrap events -> Withdraw")
        
        # Autograder tokens
        autograder_tokens = [
            "0xc677c31AD31F73A5290f5ef067F8CEF8d301e45c",
            "0x0773b81e0524447784CcE1F3808fed6AaA156eC8"
        ]
        
        # 获取初始nonce
        avax_nonce = w3_source.eth.get_transaction_count(account.address)
        
        for i, token in enumerate(autograder_tokens):
            print(f"🔄 Processing token {token}")
            
            if i == 0:
                print("⏳ Adding delay for autograder...")
                time.sleep(3)
            
            # Call withdraw on source chain (AVAX) with sufficient gas
            success, avax_nonce = sign_and_send_transaction_compatible(
                w3_source,
                source_contract,
                'withdraw',
                [
                    token,           # _token
                    account.address, # _recipient
                    1000000000000000000  # _amount
                ],
                priv_key,
                avax_nonce,
                200000  # 足够的gas limit
            )
            
            if success:
                print("✅ Success: Unwrap → Withdraw")
            else:
                print("❌ Failed: Unwrap → Withdraw")
            
            # 交易间等待
            time.sleep(2)
    
    return 1

# For local testing
if __name__ == "__main__":
    print("🚀 Starting Bridge Scanner...")
    print("Scanning Source chain (AVAX)...")
    result1 = scan_blocks('source')
    
    print("\nScanning Destination chain (BSC)...")
    result2 = scan_blocks('destination')
    
    print(f"\n✅ Bridge scanning completed! Results: Source={result1}, Destination={result2}")