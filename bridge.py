# bridge.py - FIXED IMPORT VERSION
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware  # CORRECT IMPORT NAME
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
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)  # CORRECT MIDDLEWARE
    return w3

def getContractInfo(chain):
    """
    Load the contract information from the contract_info.json file
    """
    with open(contract_info_file, 'r') as file:
        contracts = json.load(file)
    return contracts[chain]

def scan_blocks(chain):
    """
    Scan blocks for events and act upon them.
    """
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
    contract_info = getContractInfo(chain)
    contract_address = contract_info["address"]
    contract_abi = contract_info["abi"]

    contract = w3.eth.contract(address=contract_address, abi=contract_abi)
    latest_block = w3.eth.block_number
    start_block = max(latest_block - 500, 0)  # Scan more blocks

    try:
        event_class = getattr(contract.events, event_name)
        event_filter = event_class.createFilter(fromBlock=start_block, toBlock="latest")
        events = event_filter.get_all_entries()
        print(f"Found {len(events)} {event_name} events on {chain_name}.")

        for event in events:
            print(f"Processing event: {event}")
            handler(event)
        return 1

    except AttributeError as e:
        print(f"Error: Event '{event_name}' not defined in the contract's ABI: {e}")
        return 1
    except Exception as e:
        print(f"Error scanning blocks on {chain_name}: {e}")
        return 1

def handleDepositEvent(event):
    """
    Handle Deposit events from the source chain
    """
    destination_contract_info = getContractInfo("destination")
    w3 = connectTo(destination_chain)
    contract = w3.eth.contract(address=destination_contract_info["address"], abi=destination_contract_info["abi"])
    
    # Get current nonce
    account = Account.from_key(warden_private_key)
    nonce = w3.eth.get_transaction_count(account.address)
    
    tx = contract.functions.wrap(
        event.args["token"],
        event.args["recipient"],
        event.args["amount"]
    ).build_transaction({
        "chainId": w3.eth.chain_id,
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
        "nonce": nonce,
    })

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=warden_private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print(f"Wrap transaction sent: {tx_hash.hex()}")
    
    # Wait for confirmation
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt.status == 1:
            print(f"✅ Wrap transaction confirmed")
        else:
            print(f"❌ Wrap transaction failed")
    except:
        print(f"⚠️ Could not confirm transaction")

def handleUnwrapEvent(event):
    """
    Handle Unwrap events from the destination chain
    """
    source_contract_info = getContractInfo("source")
    w3 = connectTo(source_chain)
    contract = w3.eth.contract(address=source_contract_info["address"], abi=source_contract_info["abi"])
    
    # Get current nonce
    account = Account.from_key(warden_private_key)
    nonce = w3.eth.get_transaction_count(account.address)
    
    tx = contract.functions.withdraw(
        event.args["underlying_token"],
        event.args["to"],
        event.args["amount"]
    ).build_transaction({
        "chainId": w3.eth.chain_id,
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
        "nonce": nonce,
    })

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=warden_private_key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print(f"Withdraw transaction sent: {tx_hash.hex()}")
    
    # Wait for confirmation
    try:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        if receipt.status == 1:
            print(f"✅ Withdraw transaction confirmed")
        else:
            print(f"❌ Withdraw transaction failed")
    except:
        print(f"⚠️ Could not confirm transaction")

if __name__ == "__main__":
    print("🚀 Bridge Scanner - Starting")
    print("🔍 Checking source chain...")
    scanBlocks("source")
    print("\n🔍 Checking destination chain...")
    scanBlocks("destination")
    print("\n✅ Done")