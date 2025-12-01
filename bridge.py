from web3 import Web3
from web3.middleware import geth_poa_middleware
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
    w3.middleware_onion.inject(geth_poa_middleware, layer=0)  # For POA chains
    return w3

def getContractInfo(chain):
    """
    Load the contract information from the contract_info.json file
    """
    with open(contract_info_file, 'r') as file:
        contracts = json.load(file)
    return contracts[chain]

def scanBlocks(chain):
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
    start_block = max(latest_block - 5, 0)

    try:
        event_class = getattr(contract.events, event_name)  # Dynamically access the event
        event_filter = event_class.create_filter(fromBlock=start_block, toBlock="latest")
        events = event_filter.get_all_entries()
        print(f"Found {len(events)} {event_name} events on {chain_name}.")

        for event in events:
            print(f"Processing event: {event}")
            handler(event)

    except AttributeError as e:
        print(f"Error: Event '{event_name}' not defined in the contract's ABI: {e}")
    except Exception as e:
        print(f"Error scanning blocks on {chain_name}: {e}")

def handleDepositEvent(event):
    """
    Handle Deposit events from the source chain
    """
    destination_contract_info = getContractInfo("destination")
    w3 = connectTo(destination_chain)
    contract = w3.eth.contract(address=destination_contract_info["address"], abi=destination_contract_info["abi"])
    tx = contract.functions.wrap(
        event.args["token"],
        event.args["recipient"],
        event.args["amount"]
    ).buildTransaction({
        "chainId": w3.eth.chain_id,
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.getTransactionCount(Account.from_key(warden_private_key).address),
    })

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=warden_private_key)
    w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    print(f"Wrap transaction sent: {signed_tx.hash.hex()}")

def handleUnwrapEvent(event):
    """
    Handle Unwrap events from the destination chain
    """
    source_contract_info = getContractInfo("source")
    w3 = connectTo(source_chain)
    contract = w3.eth.contract(address=source_contract_info["address"], abi=source_contract_info["abi"])
    tx = contract.functions.withdraw(
        event.args["underlying_token"],
        event.args["to"],
        event.args["amount"]
    ).buildTransaction({
        "chainId": w3.eth.chain_id,
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
        "nonce": w3.eth.getTransactionCount(Account.from_key(warden_private_key).address),
    })

    signed_tx = w3.eth.account.sign_transaction(tx, private_key=warden_private_key)
    w3.eth.send_raw_transaction(signed_tx.rawTransaction)
    print(f"Withdraw transaction sent: {signed_tx.hash.hex()}")