#!/usr/bin/env python3
"""
Bridge Listener Script
"""

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
import json

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
    return int(w3.eth.gas_price * 1.2)


def _nonce(w3, acct):
    """Always fetch a fresh nonce to avoid 'nonce too low'."""
    return w3.eth.get_transaction_count(acct.address)


def topic(signature_text):
    """Produce a valid 0x-prefixed keccak hash for event filter topics."""
    h = Web3.keccak(text=signature_text)
    hx = h.hex()
    if not hx.startswith("0x"):
        hx = "0x" + hx
    return hx.lower()


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


def _scan_blocks_in_batches(w3, contract, event_name, from_block, to_block, batch_size=2048):
    """
    Scan blocks in batches to avoid RPC limits.
    """
    events = []
    current_block = from_block
    
    while current_block <= to_block:
        batch_to = min(current_block + batch_size - 1, to_block)
        
        try:
            # Get event logs for this batch
            event_filter = contract.events[event_name].create_filter(
                fromBlock=current_block,
                toBlock=batch_to
            )
            batch_events = event_filter.get_all_entries()
            events.extend(batch_events)
            
        except Exception as e:
            # If batch is still too large, try smaller batch
            if "requested too many blocks" in str(e):
                print(f"Batch too large, reducing batch size from {batch_size}...")
                return _scan_blocks_in_batches(w3, contract, event_name, from_block, to_block, batch_size // 2)
            else:
                raise
        
        current_block = batch_to + 1
    
    return events


# ================== Event Handlers ================== #

def _scan_deposit(acct, w3s, w3d, src, dst):
    """
    Grader has sent a Deposit on SOURCE (Avalanche).
    Find Deposit events and call wrap() on DEST (BSC).
    """
    latest = w3s.eth.block_number
    # Start from a reasonable recent block to avoid scanning too many blocks
    from_block = max(0, latest - 100)  # Only scan last 100 blocks
    
    try:
        # Use batched scanning to avoid RPC limits
        events = _scan_blocks_in_batches(w3s, src, "Deposit", from_block, latest)
        
        for log in events:
            try:
                ev = src.events.Deposit().process_log(log)
                token     = _fix_addr(ev["args"]["token"])
                recipient = _fix_addr(ev["args"]["recipient"])
                amount    = int(ev["args"]["amount"])

                print(f"Processing Deposit: token={token}, recipient={recipient}, amount={amount}")

                # Call wrap() on destination
                nonce = _nonce(w3d, acct)

                tx = dst.functions.wrap(
                    token,
                    recipient,
                    amount
                ).build_transaction({
                    "from":     acct.address,
                    "nonce":    nonce,
                    "chainId":  w3d.eth.chain_id,
                    "gas":      300000,
                    "gasPrice": _boosted_gas(w3d),
                })

                signed = w3d.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
                tx_hash = w3d.eth.send_raw_transaction(signed.rawTransaction)
                print(f"Wrap transaction sent: {tx_hash.hex()}")
                
                # Wait for receipt
                receipt = w3d.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
                print(f"Wrap transaction confirmed in block {receipt.blockNumber}")
                
            except Exception as e:
                print(f"Error processing individual deposit event: {e}")
                continue
                
    except Exception as e:
        print(f"Error scanning for deposit events: {e}")


def _scan_unwrap(acct, w3s, w3d, src, dst):
    """
    Grader has sent an Unwrap on DESTINATION (BSC).
    Find Unwrap events and call withdraw() on SOURCE (Avalanche).
    """
    latest = w3d.eth.block_number
    # Start from a reasonable recent block
    from_block = max(0, latest - 100)  # Only scan last 100 blocks
    
    try:
        # Use batched scanning to avoid RPC limits
        events = _scan_blocks_in_batches(w3d, dst, "Unwrap", from_block, latest)
        
        for log in events:
            try:
                ev = dst.events.Unwrap().process_log(log)
                underlying = _fix_addr(ev["args"]["underlying_token"])
                to_addr    = _fix_addr(ev["args"]["to"])
                amount     = int(ev["args"]["amount"])

                print(f"Processing Unwrap: token={underlying}, recipient={to_addr}, amount={amount}")

                # Call withdraw() on source
                nonce = _nonce(w3s, acct)

                tx = src.functions.withdraw(
                    underlying,
                    to_addr,
                    amount
                ).build_transaction({
                    "from":     acct.address,
                    "nonce":    nonce,
                    "chainId":  w3s.eth.chain_id,
                    "gas":      300000,
                    "gasPrice": _boosted_gas(w3s),
                })

                signed = w3s.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
                tx_hash = w3s.eth.send_raw_transaction(signed.rawTransaction)
                print(f"Withdraw transaction sent: {tx_hash.hex()}")
                
                # Wait for receipt
                receipt = w3s.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
                print(f"Withdraw transaction confirmed in block {receipt.blockNumber}")
                
            except Exception as e:
                print(f"Error processing individual unwrap event: {e}")
                continue
                
    except Exception as e:
        print(f"Error scanning for unwrap events: {e}")


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
        print(f"Loaded: Account={acct.address}, Source={src.address}, Dest={dst.address}")
        
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
    print("Testing source chain...")
    scan_blocks("source")
    
    print("\nTesting destination chain...")
    scan_blocks("destination")