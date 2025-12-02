#!/usr/bin/env python3
"""
Bridge Script - Simplified for Codio Autograder
"""

import json
import csv
from web3 import Web3
from eth_account import Account
import time

# ================== CONFIGURATION ================== #
AVAX_RPC = "https://api.avax-test.network/ext/bc/C/rpc"
BSC_RPC = "https://data-seed-prebsc-1-s1.binance.org:8545/"

# Warden private key - this is CRITICAL for signing transactions
WARDEN_PRIVATE_KEY = "0x3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"

# ================== HELPER FUNCTIONS ================== #

def load_config():
    """Load contract configuration."""
    with open('contract_info.json', 'r') as f:
        config = json.load(f)
    return config

def load_tokens():
    """Load token addresses from CSV."""
    tokens = {'avax': [], 'bsc': []}
    with open('erc20s.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            chain = row['chain']
            address = Web3.to_checksum_address(row['address'])
            tokens[chain].append(address)
    return tokens

def setup_web3():
    """Setup Web3 connections for both chains."""
    # Avalanche (Source)
    w3_avax = Web3(Web3.HTTPProvider(AVAX_RPC))
    
    # BSC (Destination) 
    w3_bsc = Web3(Web3.HTTPProvider(BSC_RPC))
    
    # Add POA middleware for BSC if available
    try:
        from web3.middleware import geth_poa_middleware
        w3_bsc.middleware_onion.inject(geth_poa_middleware, layer=0)
    except ImportError:
        try:
            from web3.middleware import ExtraDataToPOAMiddleware
            w3_bsc.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        except ImportError:
            pass  # Continue without middleware
    
    return w3_avax, w3_bsc

# ================== MAIN BRIDGE FUNCTION ================== #

def scan_blocks(chain_type='source', from_block=0, to_block='latest'):
    """
    Main function called by autograder.
    
    When chain_type == 'source': 
      - Look for Deposit events on Avalanche
      - Call wrap() on BSC for each deposit
    
    When chain_type == 'destination':
      - Look for Unwrap events on BSC  
      - Call withdraw() on Avalanche for each unwrap
    """
    print(f"Bridge: scan_blocks called for {chain_type} chain")
    
    try:
        # Load configuration
        config = load_config()
        tokens = load_tokens()
        
        # Setup Web3
        w3_avax, w3_bsc = setup_web3()
        
        # Load account
        account = Account.from_key(WARDEN_PRIVATE_KEY)
        print(f"Warden account: {account.address}")
        
        # Load contracts - IMPORTANT: Use addresses from config
        source_address = Web3.to_checksum_address(config['source']['address'])
        dest_address = Web3.to_checksum_address(config['destination']['address'])
        
        source_contract = w3_avax.eth.contract(
            address=source_address,
            abi=config['source']['abi']
        )
        
        dest_contract = w3_bsc.eth.contract(
            address=dest_address, 
            abi=config['destination']['abi']
        )
        
        print(f"Source contract: {source_contract.address}")
        print(f"Destination contract: {dest_contract.address}")
        
        if chain_type == 'source':
            print("\n=== Processing Source Chain (Avalanche) ===")
            
            # Get current block
            current_block = w3_avax.eth.block_number
            scan_from = max(0, current_block - 100)  # Last 100 blocks
            
            print(f"Scanning blocks {scan_from} to {current_block} for Deposit events...")
            
            # Get Deposit events - using old web3.py compatible method
            try:
                # Method 1: Try get_logs with fromBlock/toBlock as integers
                events = source_contract.events.Deposit.get_logs(
                    fromBlock=scan_from,
                    toBlock=current_block
                )
            except TypeError:
                # Method 2: Older web3.py - create filter first
                event_filter = source_contract.events.Deposit.createFilter(
                    fromBlock=scan_from,
                    toBlock=current_block
                )
                events = event_filter.get_all_entries()
            
            print(f"Found {len(events)} Deposit events")
            
            # Process each deposit
            for event in events:
                try:
                    # Get event data
                    if hasattr(event, 'args'):
                        args = event.args
                    else:
                        args = event['args']
                    
                    token = args['token']
                    recipient = args['recipient']
                    amount = args['amount']
                    
                    print(f"\nProcessing Deposit:")
                    print(f"  Token: {token}")
                    print(f"  Recipient: {recipient}")
                    print(f"  Amount: {amount}")
                    
                    # The token address is the same on both chains per erc20s.csv
                    dest_token = Web3.to_checksum_address(token)
                    
                    # Get nonce for BSC
                    nonce = w3_bsc.eth.get_transaction_count(account.address)
                    gas_price = int(w3_bsc.eth.gas_price * 1.2)
                    
                    # Build wrap transaction
                    tx = dest_contract.functions.wrap(
                        dest_token,
                        recipient,
                        amount
                    ).build_transaction({
                        'from': account.address,
                        'nonce': nonce,
                        'chainId': 97,  # BSC Testnet
                        'gas': 300000,
                        'gasPrice': gas_price,
                    })
                    
                    # Sign and send
                    signed_tx = w3_bsc.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
                    tx_hash = w3_bsc.eth.send_raw_transaction(signed_tx.raw_transaction)
                    
                    print(f"  Sent wrap transaction: {tx_hash.hex()}")
                    
                    # Wait for confirmation
                    receipt = w3_bsc.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                    
                    if receipt.status == 1:
                        print(f"  ✓ Wrap confirmed in block {receipt.blockNumber}")
                    else:
                        print(f"  ✗ Wrap failed")
                    
                    # Small delay
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"  Error processing deposit: {str(e)[:100]}")
                    continue
        
        elif chain_type == 'destination':
            print("\n=== Processing Destination Chain (BSC) ===")
            
            # Get current block
            current_block = w3_bsc.eth.block_number
            scan_from = max(0, current_block - 100)  # Last 100 blocks
            
            print(f"Scanning blocks {scan_from} to {current_block} for Unwrap events...")
            
            # Get Unwrap events - using old web3.py compatible method
            try:
                # Method 1: Try get_logs with fromBlock/toBlock as integers
                events = dest_contract.events.Unwrap.get_logs(
                    fromBlock=scan_from,
                    toBlock=current_block
                )
            except TypeError:
                # Method 2: Older web3.py - create filter first
                event_filter = dest_contract.events.Unwrap.createFilter(
                    fromBlock=scan_from,
                    toBlock=current_block
                )
                events = event_filter.get_all_entries()
            
            print(f"Found {len(events)} Unwrap events")
            
            # Process each unwrap
            for event in events:
                try:
                    # Get event data
                    if hasattr(event, 'args'):
                        args = event.args
                    else:
                        args = event['args']
                    
                    underlying_token = args['underlying_token']
                    recipient = args['to']
                    amount = args['amount']
                    
                    print(f"\nProcessing Unwrap:")
                    print(f"  Token: {underlying_token}")
                    print(f"  Recipient: {recipient}")
                    print(f"  Amount: {amount}")
                    
                    # The token address is the same on both chains per erc20s.csv
                    source_token = Web3.to_checksum_address(underlying_token)
                    
                    # Get nonce for Avalanche
                    nonce = w3_avax.eth.get_transaction_count(account.address)
                    gas_price = int(w3_avax.eth.gas_price * 1.2)
                    
                    # Build withdraw transaction
                    tx = source_contract.functions.withdraw(
                        source_token,
                        recipient,
                        amount
                    ).build_transaction({
                        'from': account.address,
                        'nonce': nonce,
                        'chainId': 43113,  # Avalanche Fuji
                        'gas': 300000,
                        'gasPrice': gas_price,
                    })
                    
                    # Sign and send
                    signed_tx = w3_avax.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
                    tx_hash = w3_avax.eth.send_raw_transaction(signed_tx.raw_transaction)
                    
                    print(f"  Sent withdraw transaction: {tx_hash.hex()}")
                    
                    # Wait for confirmation
                    receipt = w3_avax.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                    
                    if receipt.status == 1:
                        print(f"  ✓ Withdraw confirmed in block {receipt.blockNumber}")
                    else:
                        print(f"  ✗ Withdraw failed")
                    
                    # Small delay
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"  Error processing unwrap: {str(e)[:100]}")
                    continue
        
        print(f"\n✓ scan_blocks for {chain_type} completed successfully")
        return True
        
    except Exception as e:
        print(f"\n✗ Error in scan_blocks: {e}")
        import traceback
        traceback.print_exc()
        return False


# ================== TEST FUNCTION ================== #

def test_bridge():
    """Test function to verify bridge setup."""
    print("=" * 60)
    print("Testing Bridge Setup")
    print("=" * 60)
    
    try:
        # Load config
        config = load_config()
        print(f"✓ Loaded contract_info.json")
        print(f"  Source: {config['source']['address'][:20]}...")
        print(f"  Destination: {config['destination']['address'][:20]}...")
        
        # Load tokens
        tokens = load_tokens()
        print(f"✓ Loaded {len(tokens['avax'])} AVAX tokens and {len(tokens['bsc'])} BSC tokens")
        
        # Setup Web3
        w3_avax, w3_bsc = setup_web3()
        print(f"✓ Web3 connections established")
        print(f"  AVAX connected: {w3_avax.is_connected()}")
        print(f"  BSC connected: {w3_bsc.is_connected()}")
        
        # Load account
        account = Account.from_key(WARDEN_PRIVATE_KEY)
        print(f"✓ Warden account: {account.address}")
        
        # Check balances
        avax_balance = w3_avax.eth.get_balance(account.address)
        bsc_balance = w3_bsc.eth.get_balance(account.address)
        print(f"✓ Balances:")
        print(f"  AVAX: {w3_avax.from_wei(avax_balance, 'ether')} AVAX")
        print(f"  BSC: {w3_bsc.from_wei(bsc_balance, 'ether')} BNB")
        
        print("\n" + "=" * 60)
        print("Bridge setup is complete and ready!")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        return False


# ================== MAIN EXECUTION ================== #

if __name__ == "__main__":
    # Run test
    test_bridge()
    
    # You can also test scan_blocks directly
    # print("\n" + "=" * 60)
    # print("Testing scan_blocks for source chain...")
    # print("=" * 60)
    # scan_blocks('source')
    
    # print("\n" + "=" * 60)
    # print("Testing scan_blocks for destination chain...")
    # print("=" * 60)
    # scan_blocks('destination')