#!/usr/bin/env python3
"""
Bridge Listener Script
This script monitors both source (Avalanche) and destination (BNB) contracts,
and triggers corresponding actions when events are detected.
"""

import json
import time
import csv
from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account
from eth_account.signers.local import LocalAccount
from typing import Dict, Any, Tuple
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BridgeListener:
    def __init__(self, config_file: str = "contract_info.json", erc20_file: str = "erc20s.csv"):
        """
        Initialize the bridge listener with contract info and private key.
        
        Args:
            config_file: Path to contract_info.json
            erc20_file: Path to erc20s.csv
        """
        # Load contract info
        with open(config_file, 'r') as f:
            self.contract_info = json.load(f)
        
        # Load ERC20 tokens
        self.erc20_tokens = self._load_erc20_tokens(erc20_file)
        
        # Network RPC endpoints (Avalanche Fuji and BNB Testnet)
        self.networks = {
            'avax': 'https://api.avax-test.network/ext/bc/C/rpc',
            'bsc': 'https://data-seed-prebsc-1-s1.binance.org:8545/'
        }
        
        # Initialize Web3 connections
        self.w3_avax = Web3(Web3.HTTPProvider(self.networks['avax']))
        self.w3_bsc = Web3(Web3.HTTPProvider(self.networks['bsc']))
        
        # Add POA middleware for BSC
        self.w3_bsc.middleware_onion.inject(geth_poa_middleware, layer=0)
        
        # Load contract ABIs and addresses
        self.source_contract = self._load_contract(
            self.w3_avax,
            self.contract_info['source']['address'],
            self.contract_info['source']['abi']
        )
        
        self.dest_contract = self._load_contract(
            self.w3_bsc,
            self.contract_info['destination']['address'],
            self.contract_info['destination']['abi']
        )
        
        # Private key for signing transactions (you need to set this)
        # IMPORTANT: In production, use environment variables or secure storage
        self.private_key = "0x3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"
        
        
        # Event filters
        self.deposit_filter = self.source_contract.events.Deposit.create_filter(fromBlock='latest')
        self.unwrap_filter = self.dest_contract.events.Unwrap.create_filter(fromBlock='latest')
        
        # Track processed events to avoid duplicates
        self.processed_events = set()
        
        logger.info(f"Bridge listener initialized")
        logger.info(f"Source contract: {self.source_contract.address}")
        logger.info(f"Destination contract: {self.dest_contract.address}")
        logger.info(f"Warden address: {self.account.address}")
        
    def _load_erc20_tokens(self, erc20_file: str) -> Dict[str, Dict[str, str]]:
        """Load ERC20 tokens from CSV file."""
        tokens = {'avax': {}, 'bsc': {}}
        
        with open(erc20_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                chain = row['chain']
                address = row['address']
                # Store checksummed address
                tokens[chain][address.lower()] = Web3.to_checksum_address(address)
        
        logger.info(f"Loaded ERC20 tokens: {tokens}")
        return tokens
    
    def _load_contract(self, w3: Web3, address: str, abi: list) -> Any:
        """Load a contract instance."""
        checksum_address = Web3.to_checksum_address(address)
        return w3.eth.contract(address=checksum_address, abi=abi)
    
    def _get_private_key(self) -> str:
        """
        Get the private key for the warden.
        IMPORTANT: In production, use environment variables or secure key management.
        For this assignment, you need to replace with your actual private key.
        """
        # This is a placeholder - you MUST replace this with your actual private key
        # Example: return os.environ.get('WARDEN_PRIVATE_KEY')
        return "YOUR_PRIVATE_KEY_HERE"  # Replace with actual private key
    
    def get_token_address(self, source_token: str, target_chain: str) -> str:
        """
        Get the corresponding token address on the target chain.
        Based on the CSV file, the same addresses are used on both chains.
        """
        source_token_lower = source_token.lower()
        
        # Check if token exists in our mapping
        if source_token_lower in self.erc20_tokens['avax']:
            # For AVAX tokens going to BSC
            if target_chain == 'bsc':
                return self.erc20_tokens['bsc'].get(source_token_lower, source_token)
        elif source_token_lower in self.erc20_tokens['bsc']:
            # For BSC tokens going to AVAX
            if target_chain == 'avax':
                return self.erc20_tokens['avax'].get(source_token_lower, source_token)
        
        # If no mapping found, return the same address
        return source_token
    
    def handle_deposit_event(self, event: Dict[str, Any]) -> None:
        """
        Handle Deposit event from source contract.
        Calls wrap() on destination contract.
        """
        event_id = f"deposit_{event['transactionHash'].hex()}_{event['logIndex']}"
        
        if event_id in self.processed_events:
            logger.info(f"Deposit event already processed: {event_id}")
            return
        
        logger.info(f"Processing Deposit event: {event_id}")
        
        # Extract event parameters
        token = event['args']['token']
        recipient = event['args']['recipient']
        amount = event['args']['amount']
        
        logger.info(f"Deposit details - Token: {token}, Recipient: {recipient}, Amount: {amount}")
        
        # Get corresponding token address on destination chain
        dest_token = self.get_token_address(token, 'bsc')
        
        # Prepare wrap transaction on destination contract
        try:
            # Build transaction
            nonce = self.w3_bsc.eth.get_transaction_count(self.account.address)
            gas_price = self.w3_bsc.eth.gas_price
            
            wrap_tx = self.dest_contract.functions.wrap(
                dest_token,
                recipient,
                amount
            ).build_transaction({
                'chainId': 97,  # BSC Testnet
                'gas': 200000,
                'gasPrice': gas_price,
                'nonce': nonce,
            })
            
            # Sign transaction
            signed_tx = self.w3_bsc.eth.account.sign_transaction(wrap_tx, self.private_key)
            
            # Send transaction
            tx_hash = self.w3_bsc.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            # Wait for transaction receipt
            receipt = self.w3_bsc.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status == 1:
                logger.info(f"Wrap transaction successful: {tx_hash.hex()}")
                self.processed_events.add(event_id)
            else:
                logger.error(f"Wrap transaction failed: {tx_hash.hex()}")
                
        except Exception as e:
            logger.error(f"Error processing deposit event: {e}")
    
    def handle_unwrap_event(self, event: Dict[str, Any]) -> None:
        """
        Handle Unwrap event from destination contract.
        Calls withdraw() on source contract.
        """
        event_id = f"unwrap_{event['transactionHash'].hex()}_{event['logIndex']}"
        
        if event_id in self.processed_events:
            logger.info(f"Unwrap event already processed: {event_id}")
            return
        
        logger.info(f"Processing Unwrap event: {event_id}")
        
        # Extract event parameters
        underlying_token = event['args']['underlying_token']
        wrapped_token = event['args']['wrapped_token']
        recipient = event['args']['to']
        amount = event['args']['amount']
        
        logger.info(f"Unwrap details - Underlying: {underlying_token}, "
                   f"Wrapped: {wrapped_token}, Recipient: {recipient}, Amount: {amount}")
        
        # Get corresponding token address on source chain
        # Since unwrap provides both underlying and wrapped, we use underlying
        source_token = self.get_token_address(underlying_token, 'avax')
        
        # Prepare withdraw transaction on source contract
        try:
            # Build transaction
            nonce = self.w3_avax.eth.get_transaction_count(self.account.address)
            gas_price = self.w3_avax.eth.gas_price
            
            withdraw_tx = self.source_contract.functions.withdraw(
                source_token,
                recipient,
                amount
            ).build_transaction({
                'chainId': 43113,  # Avalanche Fuji Testnet
                'gas': 200000,
                'gasPrice': gas_price,
                'nonce': nonce,
            })
            
            # Sign transaction
            signed_tx = self.w3_avax.eth.account.sign_transaction(withdraw_tx, self.private_key)
            
            # Send transaction
            tx_hash = self.w3_avax.eth.send_raw_transaction(signed_tx.raw_transaction)
            
            # Wait for transaction receipt
            receipt = self.w3_avax.eth.wait_for_transaction_receipt(tx_hash)
            
            if receipt.status == 1:
                logger.info(f"Withdraw transaction successful: {tx_hash.hex()}")
                self.processed_events.add(event_id)
            else:
                logger.error(f"Withdraw transaction failed: {tx_hash.hex()}")
                
        except Exception as e:
            logger.error(f"Error processing unwrap event: {e}")
    
    def check_events(self) -> None:
        """Check for new events on both chains."""
        try:
            # Check for Deposit events on source chain
            deposit_events = self.deposit_filter.get_new_entries()
            for event in deposit_events:
                self.handle_deposit_event(event)
            
            # Check for Unwrap events on destination chain
            unwrap_events = self.unwrap_filter.get_new_entries()
            for event in unwrap_events:
                self.handle_unwrap_event(event)
                
        except Exception as e:
            logger.error(f"Error checking events: {e}")
    
    def run_once(self) -> None:
        """
        Run a single check cycle.
        This is what the autograder will call.
        """
        logger.info("Running bridge listener check...")
        self.check_events()
        logger.info("Check complete")
    
    def run_continuous(self, interval: int = 5) -> None:
        """
        Run the bridge listener continuously (for real deployment).
        
        Args:
            interval: Polling interval in seconds
        """
        logger.info(f"Starting continuous bridge listener (polling every {interval} seconds)")
        
        while True:
            try:
                self.check_events()
                time.sleep(interval)
            except KeyboardInterrupt:
                logger.info("Bridge listener stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(interval)

def main():
    """Main function to run the bridge listener."""
    # For autograder: run a single check
    bridge = BridgeListener()
    bridge.run_once()
    
    # For actual deployment, you would use:
    # bridge.run_continuous(interval=10)

if __name__ == "__main__":
    main()