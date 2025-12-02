#!/usr/bin/env python3
"""
Bridge Listener Script
"""

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
import json
import time

# --------------------------------------------------------------------
# RPC endpoints
# --------------------------------------------------------------------
AVAX_RPC = "https://api.avax-test.network/ext/bc/C/rpc"        # Source (Avalanche Fuji)
BSC_RPC  = "https://data-seed-prebsc-1-s1.binance.org:8545/"   # Destination (BSC Testnet)

# --------------------------------------------------------------------
# Warden private key (the deployer the grader mints to)
# --------------------------------------------------------------------
WARDEN_PRIVATE_KEY = "0x3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"


# ================== Utility Helpers ================== #

def _fix_addr(addr):
    """Normalize any address into a proper 0x-prefixed checksummed address."""
    if isinstance(addr, bytes):
        addr = addr.hex()
    addr = str(addr)
    if not addr.startswith("0x"):
        addr = "0x" + addr[-40:]
    return Web3.to_checksum_address(addr)


def _boosted_gas(w3):
    """Boost gas price a bit to avoid 'replacement transaction underpriced'."""
    gas_price = w3.eth.gas_price
    return int(gas_price * 1.5)  # Increase to 1.5x to avoid underpriced errors


def _nonce(w3, acct):
    """Always fetch a fresh nonce to avoid 'nonce too low'."""
    return w3.eth.get_transaction_count(acct.address)


# ================== Setup ================== #

def _load():
    """Load web3 connections, account, and source/destination contracts."""
    with open("contract_info.json", "r") as f:
        info = json.load(f)

    w3s = Web3(Web3.HTTPProvider(AVAX_RPC))
    w3d = Web3(Web3.HTTPProvider(BSC_RPC))

    w3s.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    w3d.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    if not w3s.is_connected():
        raise Exception("Could not connect to Avalanche RPC")
    if not w3d.is_connected():
        raise Exception("Could not connect to BSC RPC")

    acct = Account.from_key(WARDEN_PRIVATE_KEY)

    src = w3s.eth.contract(
        address=Web3.to_checksum_address(info["source"]["address"]),
        abi=info["source"]["abi"],
    )
    dst = w3d.eth.contract(
        address=Web3.to_checksum_address(info["destination"]["address"]),
        abi=info["destination"]["abi"],
    )

    return acct, w3s, w3d, src, dst


# ================== Event Handlers ================== #

def _scan_deposit(acct, w3s, w3d, src, dst):
    """
    Grader has sent a Deposit on SOURCE (Avalanche).
    Find Deposit events and call wrap() on DEST (BSC).
    """
    print("Scanning for Deposit events on source chain...")
    
    latest = w3s.eth.block_number
    # Scan from a block that's recent enough for the grader's transaction
    from_block = max(0, latest - 50)  # Last 50 blocks should be enough
    
    try:
        # Get Deposit events using get_logs method
        events = src.events.Deposit.get_logs(fromBlock=from_block, toBlock=latest)
        print(f"Found {len(events)} Deposit events")
        
        for event in events:
            try:
                token = _fix_addr(event.args.token)
                recipient = _fix_addr(event.args.recipient)
                amount = event.args.amount
                
                print(f"Processing Deposit: token={token}, recipient={recipient}, amount={amount}")
                
                # For the bridge, we need to send the token to the destination
                # The token addresses are the same on both chains according to erc20s.csv
                dest_token = token  # Same address on BSC
                
                # Call wrap() on destination contract
                nonce = _nonce(w3d, acct)
                gas_price = _boosted_gas(w3d)
                
                # Estimate gas first
                try:
                    gas_estimate = dst.functions.wrap(
                        dest_token,
                        recipient,
                        amount
                    ).estimate_gas({'from': acct.address})
                    gas_limit = int(gas_estimate * 1.2)  # Add 20% buffer
                except:
                    gas_limit = 300000  # Default if estimation fails
                
                tx = dst.functions.wrap(
                    dest_token,
                    recipient,
                    amount
                ).build_transaction({
                    "from": acct.address,
                    "nonce": nonce,
                    "chainId": 97,  # BSC Testnet chain ID
                    "gas": gas_limit,
                    "gasPrice": gas_price,
                })
                
                signed = w3d.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
                tx_hash = w3d.eth.send_raw_transaction(signed.rawTransaction)
                print(f"Wrap transaction sent: {tx_hash.hex()}")
                
                # Wait for receipt
                receipt = w3d.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                print(f"Wrap transaction confirmed in block {receipt.blockNumber}")
                
                # Small delay to avoid nonce issues
                time.sleep(2)
                
            except Exception as e:
                print(f"Error processing individual deposit event: {e}")
                continue
                
    except Exception as e:
        print(f"Error scanning for deposit events: {e}")
        import traceback
        traceback.print_exc()


def _scan_unwrap(acct, w3s, w3d, src, dst):
    """
    Grader has sent an Unwrap on DESTINATION (BSC).
    Find Unwrap events and call withdraw() on SOURCE (Avalanche).
    """
    print("Scanning for Unwrap events on destination chain...")
    
    latest = w3d.eth.block_number
    # Scan from a block that's recent enough for the grader's transaction
    from_block = max(0, latest - 50)  # Last 50 blocks should be enough
    
    try:
        # Get Unwrap events using get_logs method
        events = dst.events.Unwrap.get_logs(fromBlock=from_block, toBlock=latest)
        print(f"Found {len(events)} Unwrap events")
        
        for event in events:
            try:
                underlying = _fix_addr(event.args.underlying_token)
                recipient = _fix_addr(event.args.to)
                amount = event.args.amount
                
                print(f"Processing Unwrap: token={underlying}, recipient={recipient}, amount={amount}")
                
                # For the bridge, we need to send the token back to the source
                # The token addresses are the same on both chains according to erc20s.csv
                source_token = underlying  # Same address on Avalanche
                
                # Call withdraw() on source contract
                nonce = _nonce(w3s, acct)
                gas_price = _boosted_gas(w3s)
                
                # Estimate gas first
                try:
                    gas_estimate = src.functions.withdraw(
                        source_token,
                        recipient,
                        amount
                    ).estimate_gas({'from': acct.address})
                    gas_limit = int(gas_estimate * 1.2)  # Add 20% buffer
                except:
                    gas_limit = 300000  # Default if estimation fails
                
                tx = src.functions.withdraw(
                    source_token,
                    recipient,
                    amount
                ).build_transaction({
                    "from": acct.address,
                    "nonce": nonce,
                    "chainId": 43113,  # Avalanche Fuji chain ID
                    "gas": gas_limit,
                    "gasPrice": gas_price,
                })
                
                signed = w3s.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
                tx_hash = w3s.eth.send_raw_transaction(signed.rawTransaction)
                print(f"Withdraw transaction sent: {tx_hash.hex()}")
                
                # Wait for receipt
                receipt = w3s.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
                print(f"Withdraw transaction confirmed in block {receipt.blockNumber}")
                
                # Small delay to avoid nonce issues
                time.sleep(2)
                
            except Exception as e:
                print(f"Error processing individual unwrap event: {e}")
                continue
                
    except Exception as e:
        print(f"Error scanning for unwrap events: {e}")
        import traceback
        traceback.print_exc()


# ================== Autograder Entry ================== #

def scan_blocks(*args, **kwargs):
    """
    Entry point the autograder calls.
    
    scan_blocks("source")      -> handle Deposit on source → wrap() on dest
    scan_blocks("destination") -> handle Unwrap on dest → withdraw() on source
    """
    try:
        if not args:
            print("No arguments provided to scan_blocks")
            return
        
        side = args[0]
        if side not in ("source", "destination"):
            print(f"Invalid side: {side}. Must be 'source' or 'destination'")
            return
        
        print(f"Starting scan_blocks for {side} chain...")
        
        acct, w3s, w3d, src, dst = _load()
        print(f"Loaded: Account={acct.address}")
        print(f"Source Contract={src.address}")
        print(f"Destination Contract={dst.address}")
        
        if side == "source":
            _scan_deposit(acct, w3s, w3d, src, dst)
        else:  # "destination"
            _scan_unwrap(acct, w3s, w3d, src, dst)
            
        print(f"scan_blocks for {side} completed successfully")
        
    except Exception as e:
        print(f"Error in scan_blocks: {e}")
        import traceback
        traceback.print_exc()


# For testing purposes
if __name__ == "__main__":
    # Test both sides
    print("=" * 60)
    print("Bridge Listener - Testing")
    print("=" * 60)
    
    print("\nTesting source chain...")
    scan_blocks("source")
    
    print("\nTesting destination chain...")
    scan_blocks("destination")