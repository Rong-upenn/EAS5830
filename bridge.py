# bridge.py - CORRECTED VERSION
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
import json

def connect(chain):
    if chain == "source":
        url = "https://api.avax-test.network/ext/bc/C/rpc"
    else:
        url = "https://bsc-testnet-rpc.publicnode.com"
    
    w3 = Web3(Web3.HTTPProvider(url, request_kwargs={'timeout': 60}))
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

def send_tx(w3, contract, func, args, pk, nonce, gas=300000):
    acct = Account.from_key(pk)
    print(f"📝 {func} with args={args}, nonce={nonce}")

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
        print(f"➡️ {func} tx hash: {tx_hash.hex()}")

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.status == 1:
            print(f"✅ {func} success")
            return True, nonce + 1
        else:
            print(f"❌ {func} reverted")
            return False, w3.eth.get_transaction_count(acct.address)

    except Exception as e:
        print(f"❌ {func} error: {e}")
        return False, w3.eth.get_transaction_count(acct.address)

def decode_event_data(log, event_type):
    """Decode event data based on event type"""
    if event_type == "Deposit":
        # Deposit has 2 indexed + 1 non-indexed
        if len(log['topics']) == 3:
            token = Web3.to_checksum_address('0x' + log['topics'][1].hex()[-40:])
            recipient = Web3.to_checksum_address('0x' + log['topics'][2].hex()[-40:])
            amount = int(log['data'], 16) if log['data'] != '0x' else 0
            return {
                'args': {
                    'token': token,
                    'recipient': recipient,
                    'amount': amount
                }
            }
    
    elif event_type in ["Unwrap", "Wrap"]:
        # Unwrap/Wrap have 3 indexed + 2/1 non-indexed
        if len(log['topics']) == 4:
            underlying_token = Web3.to_checksum_address('0x' + log['topics'][1].hex()[-40:])
            wrapped_token = Web3.to_checksum_address('0x' + log['topics'][2].hex()[-40:])
            recipient = Web3.to_checksum_address('0x' + log['topics'][3].hex()[-40:])
            
            # Parse data - might contain multiple values
            data = log['data']
            if data != '0x':
                # For Unwrap: data contains (address frm, uint256 amount)
                # For Wrap: data contains (uint256 amount)
                # We need to parse properly
                if len(data) >= 66:  # Has at least one 32-byte value
                    # Skip 0x prefix and take first 64 chars for amount
                    amount_hex = data[2:66]
                    amount = int(amount_hex, 16)
                else:
                    amount = 0
            else:
                amount = 0
            
            return {
                'args': {
                    'underlying_token': underlying_token,
                    'wrapped_token': wrapped_token,
                    'recipient': recipient,
                    'amount': amount
                }
            }
    
    return None

def get_events(w3, contract_address, from_block, to_block, event_type):
    """Get events using web3's built-in event parsing"""
    events = []
    
    # Load ABI based on event type
    info = get_contract_info()
    if event_type == "Deposit":
        # Get Deposit event ABI from source contract
        source_abi = info["source"]["abi"]
        contract = w3.eth.contract(address=contract_address, abi=source_abi)
        
        try:
            # Get events using web3's event filter
            event_filter = contract.events.Deposit.create_filter(
                from_block=from_block,
                to_block=to_block
            )
            events = event_filter.get_all_entries()
            print(f"📊 Found {len(events)} Deposit events using web3 filter")
        except Exception as e:
            print(f"⚠️ Could not use web3 filter for Deposit: {e}")
            events = []
    
    elif event_type in ["Unwrap", "Wrap"]:
        # Get Unwrap/Wrap event ABI from destination contract
        dest_abi = info["destination"]["abi"]
        contract = w3.eth.contract(address=contract_address, abi=dest_abi)
        
        try:
            if event_type == "Unwrap":
                event_filter = contract.events.Unwrap.create_filter(
                    from_block=from_block,
                    to_block=to_block
                )
            else:
                event_filter = contract.events.Wrap.create_filter(
                    from_block=from_block,
                    to_block=to_block
                )
            events = event_filter.get_all_entries()
            print(f"📊 Found {len(events)} {event_type} events using web3 filter")
        except Exception as e:
            print(f"⚠️ Could not use web3 filter for {event_type}: {e}")
            events = []
    
    # Fallback to manual scanning if web3 filter fails
    if not events:
        print(f"🔄 Falling back to manual scanning for {event_type} events...")
        events = get_events_manual(w3, contract_address, from_block, to_block, event_type)
    
    return events

def get_events_manual(w3, contract_address, from_block, to_block, event_type):
    """Manual event scanning as fallback"""
    events = []
    
    # Calculate event signatures
    if event_type == "Deposit":
        # Deposit(address indexed token, address indexed recipient, uint256 amount)
        event_signature = Web3.keccak(text="Deposit(address,address,uint256)").hex()
    elif event_type == "Unwrap":
        # Unwrap(address indexed underlying_token, address indexed wrapped_token, address indexed to, address frm, uint256 amount)
        event_signature = Web3.keccak(text="Unwrap(address,address,address,address,uint256)").hex()
    elif event_type == "Wrap":
        # Wrap(address indexed underlying_token, address indexed wrapped_token, address indexed to, uint256 amount)
        event_signature = Web3.keccak(text="Wrap(address,address,address,uint256)").hex()
    else:
        return events
    
    print(f"🔍 Manually scanning blocks {from_block} to {to_block} for {event_type} events...")
    
    # Scan in smaller chunks to avoid timeout
    chunk_size = 100
    for chunk_start in range(from_block, to_block + 1, chunk_size):
        chunk_end = min(chunk_start + chunk_size - 1, to_block)
        
        try:
            # Get logs directly from RPC
            logs = w3.eth.get_logs({
                'address': contract_address,
                'fromBlock': chunk_start,
                'toBlock': chunk_end,
                'topics': [event_signature]
            })
            
            for log in logs:
                decoded = decode_event_data(log, event_type)
                if decoded:
                    events.append(decoded)
                    
        except Exception as e:
            print(f"⚠️ Error scanning blocks {chunk_start}-{chunk_end}: {e}")
            continue
    
    print(f"📊 Found {len(events)} {event_type} events manually")
    return events

def scan_blocks(chain, info_path="contract_info.json"):
    pk = load_privkey()
    acct = Account.from_key(pk)
    print(f"🔑 Warden: {acct.address}")

    info = get_contract_info(info_path)
    
    try:
        w3_src = connect("source")
        w3_dst = connect("destination")
        print(f"✅ Connected to source chain: block {w3_src.eth.block_number}")
        print(f"✅ Connected to destination chain: block {w3_dst.eth.block_number}")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return 1

    source = w3_src.eth.contract(address=info["source"]["address"], abi=info["source"]["abi"])
    dest = w3_dst.eth.contract(address=info["destination"]["address"], abi=info["destination"]["abi"])

    if chain == "source":
        print("🔍 Scanning for Deposit events on source chain...")
        
        latest = w3_src.eth.block_number
        from_block = max(latest - 10000, 0)  # Scan more blocks
        
        events = get_events(w3_src, info["source"]["address"], from_block, latest, "Deposit")

        if not events:
            print("ℹ️ No Deposit events found")
            # Try scanning even more blocks
            from_block = max(latest - 20000, 0)
            events = get_events(w3_src, info["source"]["address"], from_block, latest, "Deposit")
            if not events:
                print("❌ Still no Deposit events found")
                return 1

        nonce = w3_dst.eth.get_transaction_count(acct.address)
        success_count = 0

        for ev in events:
            token = ev["args"]["token"]
            recipient = ev["args"]["recipient"]
            amount = ev["args"]["amount"]

            print(f"➡️ Processing Deposit: token={token}, recipient={recipient}, amount={amount}")

            # Check if token is approved on destination
            try:
                # Call wrap on destination
                ok, nonce = send_tx(w3_dst, dest, "wrap", [token, recipient, amount], pk, nonce, gas=400000)
                if ok:
                    success_count += 1
                    print("🎉 Wrapped successfully")
                else:
                    print("❌ Wrap failed")
            except Exception as e:
                print(f"❌ Error calling wrap: {e}")

        print(f"📈 Successfully wrapped {success_count}/{len(events)} deposits")
        return 1

    elif chain == "destination":
        print("🔍 Scanning for Unwrap events on destination chain...")
        
        latest = w3_dst.eth.block_number
        from_block = max(latest - 10000, 0)
        
        events = get_events(w3_dst, info["destination"]["address"], from_block, latest, "Unwrap")

        if not events:
            print("ℹ️ No Unwrap events found")
            # Try scanning even more blocks
            from_block = max(latest - 20000, 0)
            events = get_events(w3_dst, info["destination"]["address"], from_block, latest, "Unwrap")
            if not events:
                print("❌ Still no Unwrap events found")
                return 1

        nonce = w3_src.eth.get_transaction_count(acct.address)
        success_count = 0

        for ev in events:
            # For Unwrap events, we need to use wrapped_token to find underlying_token
            wrapped_token = ev["args"]["wrapped_token"]
            underlying_token = ev["args"]["underlying_token"]
            recipient = ev["args"]["recipient"]
            amount = ev["args"]["amount"]

            print(f"➡️ Processing Unwrap: wrapped_token={wrapped_token}, underlying_token={underlying_token}, recipient={recipient}, amount={amount}")

            # Call withdraw on source with underlying_token
            ok, nonce = send_tx(w3_src, source, "withdraw", [underlying_token, recipient, amount], pk, nonce, gas=400000)
            if ok:
                success_count += 1
                print("🎉 Withdrawn successfully")
            else:
                print("❌ Withdraw failed")

        print(f"📈 Successfully withdrew {success_count}/{len(events)} unwraps")
        return 1

    return 1

if __name__ == "__main__":
    print("🚀 Starting bridge scanner...")
    print("\n🚀 Scanning source chain for deposits")
    scan_blocks("source")
    print("\n🚀 Scanning destination chain for unwraps")  
    scan_blocks("destination")