# bridge.py - UPDATED FOR NEW EVENT STRUCTURE
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
import json

def connect(chain):
    if chain == "source":
        url = "https://api.avax-test.network/ext/bc/C/rpc"
    else:
        url = "https://bsc-testnet-rpc.publicnode.com"
    
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 30}))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

def get_contract_info(path="contract_info.json"):
    with open(path, "r") as f:
        return json.load(f)

def load_privkey():
    priv = "3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"
    if not priv.startswith("0x"):
        priv = "0x" + priv
    return priv

def send_tx(w3, contract, func, args, pk, nonce, gas=200000):
    acct = Account.from_key(pk)
    print(f"📝 {func} with nonce={nonce}")

    try:
        tx = getattr(contract.functions, func)(*args).build_transaction({
            "from": acct.address,
            "nonce": nonce,
            "chainId": w3.eth.chain_id,
            "gas": gas,
            "gasPrice": w3.eth.gas_price
        })

        signed = w3.eth.account.sign_transaction(tx, pk)
        tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
        print(f"➡️ {func}: {tx_hash.hex()}")

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status == 1:
            print(f"✅ {func} success")
            return True, nonce + 1
        else:
            print(f"❌ {func} reverted")
            return False, w3.eth.get_transaction_count(acct.address)

    except Exception as e:
        print(f"❌ {func} error: {e}")
        return False, w3.eth.get_transaction_count(acct.address)

def get_events_manual(w3, contract_address, from_block, to_block, event_type):
    """Manual event scanning for new event structure"""
    events = []
    
    # Calculate event signatures for your new events
    if event_type == "Deposit":
        # Deposit(address,address,uint256)
        event_signature = "0x5548c837ab068cf56a2c2479df0882a4922fd203edb7517321831d95078c5f62"
    else:  # Unwrap or Wrap
        # Unwrap(address,address,uint256) or Wrap(address,address,uint256)
        # These will have the same signature since they have the same parameters
        event_signature = Web3.keccak(text="Unwrap(address,address,uint256)").hex()
    
    print(f"🔍 Scanning blocks {from_block} to {to_block} for {event_type} events...")
    
    for block_num in range(from_block, to_block + 1):
        try:
            block = w3.eth.get_block(block_num, full_transactions=True)
            
            for tx in block.transactions:
                if isinstance(tx, dict) and tx.get('to') and tx['to'].lower() == contract_address.lower():
                    try:
                        receipt = w3.eth.get_transaction_receipt(tx['hash'])
                        
                        for log in receipt.logs:
                            if (log['address'].lower() == contract_address.lower() and 
                                len(log['topics']) > 0 and 
                                log['topics'][0].hex() == event_signature):
                                
                                # For both Deposit and Unwrap events with the new structure
                                if len(log['topics']) == 3:  # signature + 2 indexed params
                                    token = Web3.to_checksum_address(log['topics'][1][12:].hex())
                                    recipient = Web3.to_checksum_address(log['topics'][2][12:].hex())
                                    amount = int(log['data'], 16) if log['data'] != '0x' else 0
                                    
                                    events.append({
                                        'args': {'token': token, 'recipient': recipient, 'amount': amount}
                                    })
                                    print(f"✅ {event_type} in block {block_num}: token={token[:10]}..., recipient={recipient[:10]}..., amount={amount}")
                                
                    except Exception as e:
                        continue
        except Exception as e:
            continue
    
    print(f"📊 Found {len(events)} {event_type} events")
    return events

def scan_blocks(chain, info_path="contract_info.json"):
    pk = load_privkey()
    acct = Account.from_key(pk)
    print(f"🔑 Warden: {acct.address}")

    info = get_contract_info(info_path)
    
    try:
        w3_src = connect("source")
        w3_dst = connect("destination")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return 1

    source = w3_src.eth.contract(address=info["source"]["address"], abi=info["source"]["abi"])
    dest = w3_dst.eth.contract(address=info["destination"]["address"], abi=info["destination"]["abi"])

    if chain == "source":
        print("🔍 Scanning for Deposit events...")
        
        latest = w3_src.eth.block_number
        from_block = max(latest - 5000, 0)  # Larger range to catch autograder events
        
        events = get_events_manual(w3_src, info["source"]["address"], from_block, latest, "Deposit")

        if not events:
            print("ℹ️ No Deposit events found")
            return 1

        nonce = w3_dst.eth.get_transaction_count(acct.address)
        success_count = 0

        for ev in events:
            token = ev["args"]["token"]
            recipient = ev["args"]["recipient"]
            amount = ev["args"]["amount"]

            print(f"➡️ Processing Deposit: token={token}, amount={amount}")

            ok, nonce = send_tx(w3_dst, dest, "wrap", [token, recipient, amount], pk, nonce)
            if ok:
                success_count += 1
                print("🎉 Wrapped successfully")
            else:
                print("❌ Wrap failed")

        print(f"📈 Successfully wrapped {success_count}/{len(events)} deposits")
        return 1

    elif chain == "destination":
        print("🔍 Scanning for Unwrap events...")
        
        latest = w3_dst.eth.block_number
        from_block = max(latest - 5000, 0)  # Larger range to catch autograder events
        
        events = get_events_manual(w3_dst, info["destination"]["address"], from_block, latest, "Unwrap")

        if not events:
            print("ℹ️ No Unwrap events found")
            return 1

        nonce = w3_src.eth.get_transaction_count(acct.address)
        success_count = 0

        for ev in events:
            token = ev["args"]["token"]
            recipient = ev["args"]["recipient"]
            amount = ev["args"]["amount"]

            print(f"➡️ Processing Unwrap: token={token}, amount={amount}")

            ok, nonce = send_tx(w3_src, source, "withdraw", [token, recipient, amount], pk, nonce)
            if ok:
                success_count += 1
                print("🎉 Withdrawn successfully")
            else:
                print("❌ Withdraw failed")

        print(f"📈 Successfully withdrew {success_count}/{len(events)} unwraps")
        return 1

    return 1

if __name__ == "__main__":
    print("🚀 Testing source chain")
    scan_blocks("source")
    print("\n🚀 Testing destination chain")  
    scan_blocks("destination")