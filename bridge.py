
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
import json
from eth_account import Account

# Constants
source_chain = 'avax'
destination_chain = 'bsc'
contract_info_file = "contract_info.json"
warden_private_key = "0x3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"

def connectTo(chain):
    """
    Connect to the blockchain
    """
    if chain == 'avax':
        api_url = "https://api.avax-test.network/ext/bc/C/rpc"
    elif chain == 'bsc':
        api_url = "https://data-seed-prebsc-1-s1.binance.org:8545/"
    else:
        raise ValueError("Invalid chain specified.")
    
    w3 = Web3(Web3.HTTPProvider(api_url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

def getContractInfo(info_path="contract_info.json"):
    """
    Load the contract information from the contract_info.json file
    """
    with open(info_path, 'r') as file:
        contracts = json.load(file)
    return contracts

def scan_blocks(chain, info_path="contract_info.json"):
    """
    Scan blocks for events and act upon them.
    """
    print(f"🔍 Scanning {chain} chain with contract info from {info_path}")
    
    if chain == "source":
        chain_name = "avax"
        event_name = "Deposit"
        handler = handleDepositEvent
    elif chain == "destination":
        chain_name = "bsc"
        event_name = "Unwrap"
        handler = handleUnwrapEvent
    else:
        raise ValueError("Invalid chain specified.")
    
    w3 = connectTo(chain_name)
    contracts = getContractInfo(info_path)
    
    if chain == "source":
        contract_info = contracts["source"]
    else:
        contract_info = contracts["destination"]
        
    contract_address = contract_info["address"]
    contract_abi = contract_info["abi"]

    contract = w3.eth.contract(address=contract_address, abi=contract_abi)
    latest_block = w3.eth.block_number
    start_block = max(latest_block - 1000, 0)  # Scan more blocks

    try:
        print(f"📊 Scanning blocks {start_block} to {latest_block}")
        
        # FIXED: Use create_filter() not createFilter()
        event_class = getattr(contract.events, event_name)
        event_filter = event_class.create_filter(fromBlock=start_block, toBlock="latest")
        events = event_filter.get_all_entries()
        
        print(f"📈 Found {len(events)} {event_name} events on {chain_name}.")

        for event in events:
            print(f"➡️ Processing {event_name} event...")
            handler(event, info_path)
        return 1

    except AttributeError as e:
        print(f"❌ Error: Event '{event_name}' not defined in the contract's ABI: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error scanning blocks on {chain_name}: {e}")
        # Try alternative method
        print("🔄 Trying alternative event scanning method...")
        return scan_events_alternative(w3, contract_address, contract_abi, event_name, start_block, latest_block, handler, info_path)

def scan_events_alternative(w3, contract_address, contract_abi, event_name, from_block, to_block, handler, info_path):
    """Alternative method to scan events if create_filter fails"""
    try:
        contract = w3.eth.contract(address=contract_address, abi=contract_abi)
        
        # Get logs directly
        if event_name == "Deposit":
            event_signature = w3.keccak(text="Deposit(address,address,uint256)").hex()
        elif event_name == "Unwrap":
            event_signature = w3.keccak(text="Unwrap(address,address,address,address,uint256)").hex()
        else:
            return 1
        
        logs = w3.eth.get_logs({
            'address': contract_address,
            'fromBlock': from_block,
            'toBlock': to_block,
            'topics': [event_signature]
        })
        
        print(f"📊 Found {len(logs)} {event_name} events via direct logs")
        
        for log in logs:
            # Create a simple event-like object
            if len(log['topics']) >= 3:
                event_dict = {'args': {}}
                
                if event_name == "Deposit":
                    event_dict['args']['token'] = Web3.to_checksum_address('0x' + log['topics'][1].hex()[-40:])
                    event_dict['args']['recipient'] = Web3.to_checksum_address('0x' + log['topics'][2].hex()[-40:])
                    event_dict['args']['amount'] = int(log['data'], 16) if log['data'] != '0x' else 0
                
                elif event_name == "Unwrap":
                    event_dict['args']['underlying_token'] = Web3.to_checksum_address('0x' + log['topics'][1].hex()[-40:])
                    event_dict['args']['wrapped_token'] = Web3.to_checksum_address('0x' + log['topics'][2].hex()[-40:])
                    event_dict['args']['to'] = Web3.to_checksum_address('0x' + log['topics'][3].hex()[-40:])
                    # Amount is in data
                    if log['data'] != '0x' and len(log['data']) >= 66:
                        amount_hex = log['data'][2:66]  # First 32 bytes
                        event_dict['args']['amount'] = int(amount_hex, 16)
                    else:
                        event_dict['args']['amount'] = 0
                
                print(f"➡️ Processing {event_name} event...")
                handler(event_dict, info_path)
        
        return 1
        
    except Exception as e:
        print(f"❌ Alternative scanning also failed: {e}")
        return 1

def handleDepositEvent(event, info_path="contract_info.json"):
    """
    Handle Deposit events from the source chain
    """
    try:
        contracts = getContractInfo(info_path)
        destination_contract_info = contracts["destination"]
        
        w3 = connectTo(destination_chain)
        contract = w3.eth.contract(address=destination_contract_info["address"], abi=destination_contract_info["abi"])
        
        account = Account.from_key(warden_private_key)
        nonce = w3.eth.get_transaction_count(account.address)
        
        print(f"📤 Wrapping: token={event['args']['token']}, amount={event['args']['amount']}")
        
        tx = contract.functions.wrap(
            event['args']['token'],
            event['args']['recipient'],
            event['args']['amount']
        ).build_transaction({
            "chainId": w3.eth.chain_id,
            "gas": 300000,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key=warden_private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"✅ Wrap transaction sent: {tx_hash.hex()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error handling deposit: {e}")
        return False

def handleUnwrapEvent(event, info_path="contract_info.json"):
    """
    Handle Unwrap events from the destination chain
    """
    try:
        contracts = getContractInfo(info_path)
        source_contract_info = contracts["source"]
        
        w3 = connectTo(source_chain)
        contract = w3.eth.contract(address=source_contract_info["address"], abi=source_contract_info["abi"])
        
        account = Account.from_key(warden_private_key)
        nonce = w3.eth.get_transaction_count(account.address)
        
        print(f"📤 Withdrawing: token={event['args']['underlying_token']}, amount={event['args']['amount']}")
        
        tx = contract.functions.withdraw(
            event['args']['underlying_token'],
            event['args']['to'],
            event['args']['amount']
        ).build_transaction({
            "chainId": w3.eth.chain_id,
            "gas": 300000,
            "gasPrice": w3.eth.gas_price,
            "nonce": nonce,
        })

        signed_tx = w3.eth.account.sign_transaction(tx, private_key=warden_private_key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print(f"✅ Withdraw transaction sent: {tx_hash.hex()}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error handling unwrap: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Bridge Scanner - Starting")
    print("🔍 Checking source chain...")
    scan_blocks("source")
    print("\n🔍 Checking destination chain...")
    scan_blocks("destination")
    print("\n✅ Done")