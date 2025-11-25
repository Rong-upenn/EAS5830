# bridge.py - ULTIMATE ROBUST VERSION
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
import json

# ----------------------
# Connections
# ----------------------
def connect(chain):
    if chain == "source":  # Avalanche Fuji
        url = "https://api.avax-test.network/ext/bc/C/rpc"
    else:  # BSC Testnet
        url = "https://data-seed-prebsc-1-s1.binance.org:8545/"

    w3 = Web3(Web3.HTTPProvider(url))
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3

# ----------------------
# Load contract info
# ----------------------
def get_contract_info(path="contract_info.json"):
    with open(path, "r") as f:
        return json.load(f)

# ----------------------
# Load private key
# ----------------------
def load_privkey():
    priv = "3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"
    if not priv:
        raise Exception("❌ Private key missing in bridge.py")

    if not priv.startswith("0x"):
        priv = "0x" + priv

    return priv

# ----------------------
# Sign + Send
# ----------------------
def send_tx(w3, contract, func, args, pk, nonce, gas=200000):
    acct = Account.from_key(pk)
    print(f"📝 nonce={nonce}, gas={gas}")

    try:
        tx = getattr(contract.functions, func)(*args).build_transaction({
            "from": acct.address,
            "nonce": nonce,
            "chainId": w3.eth.chain_id,
            "gas": gas,
            "gasPrice": w3.eth.gas_price
        })

        signed = w3.eth.account.sign_transaction(tx, pk)
        raw = signed.rawTransaction

        tx_hash = w3.eth.send_raw_transaction(raw)
        print(f"➡️ sent {func}: {tx_hash.hex()}")

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            print(f"✅ {func} success in block {receipt.blockNumber}")
            return True, nonce + 1
        else:
            print(f"❌ {func} reverted")
            return False, w3.eth.get_transaction_count(acct.address)

    except Exception as e:
        print(f"❌ TX error in {func}: {e}")
        return False, w3.eth.get_transaction_count(acct.address)

# ----------------------
# Event decoding functions
# ----------------------
def decode_deposit_event(log):
    """Decode Deposit event manually"""
    deposit_signature = "0x5548c837ab068cf56a2c2479df0882a4922fd203edb7517321831d95078c5f62"
    
    if len(log['topics']) > 0 and log['topics'][0].hex() == deposit_signature:
        if len(log['topics']) == 3:  # signature + 2 indexed params
            token = Web3.to_checksum_address(log['topics'][1][12:].hex())
            recipient = Web3.to_checksum_address(log['topics'][2][12:].hex())
            amount = int(log['data'], 16) if log['data'] != '0x' else 0
            
            return {
                'args': {
                    'token': token,
                    'recipient': recipient,
                    'amount': amount
                }
            }
    return None

def decode_unwrap_event(log):
    """Decode Unwrap event manually - all parameters in data"""
    unwrap_signature = "0xbe8e6aacbb5d99c99f1992d91d807f570d0acacabee02374369ed42710dc6698"
    
    if len(log['topics']) > 0 and log['topics'][0].hex() == unwrap_signature:
        data = log['data']
        if len(data) == 96:  # 3 parameters * 32 bytes each
            # Parse: token (32 bytes), recipient (32 bytes), amount (32 bytes)
            token_bytes = data[0:32]
            recipient_bytes = data[32:64] 
            amount_bytes = data[64:96]
            
            # Convert to proper types
            token = Web3.to_checksum_address(token_bytes[12:].hex())
            recipient = Web3.to_checksum_address(recipient_bytes[12:].hex())
            amount = int.from_bytes(amount_bytes, 'big')
            
            return {
                'args': {
                    'token': token,
                    'recipient': recipient,
                    'amount': amount
                }
            }
    return None

def scan_blocks_for_events(w3, contract_address, from_block, to_block, event_type):
    """Scan blocks for specific events with detailed logging"""
    events = []
    print(f"🔍 Scanning blocks {from_block} to {to_block} for {event_type} events...")
    
    blocks_scanned = 0
    blocks_with_contract_txs = 0
    
    for block_num in range(from_block, to_block + 1):
        try:
            block = w3.eth.get_block(block_num, full_transactions=True)
            blocks_scanned += 1
            
            contract_txs_in_block = 0
            for tx in block.transactions:
                if isinstance(tx, dict) and tx.get('to') and tx['to'].lower() == contract_address.lower():
                    contract_txs_in_block += 1
                    try:
                        receipt = w3.eth.get_transaction_receipt(tx['hash'])
                        for log in receipt.logs:
                            if log['address'].lower() == contract_address.lower():
                                if event_type == "Deposit":
                                    decoded = decode_deposit_event(log)
                                elif event_type == "Unwrap":
                                    decoded = decode_unwrap_event(log)
                                
                                if decoded:
                                    events.append(decoded)
                                    print(f"✅ Found {event_type} event in block {block_num}, tx: {tx['hash'].hex()}")
                                    print(f"   Details: {decoded['args']}")
                    except Exception as e:
                        continue
            
            if contract_txs_in_block > 0:
                blocks_with_contract_txs += 1
                print(f"📦 Block {block_num}: {contract_txs_in_block} contract transactions")
                        
        except Exception as e:
            # Skip blocks that can't be read
            continue
    
    print(f"📊 Scan completed: {blocks_scanned} blocks scanned, {blocks_with_contract_txs} blocks with contract txs, {len(events)} {event_type} events found")
    return events

# ----------------------
# Event-driven bridge logic - MAIN FUNCTION
# ----------------------
def scan_blocks(chain, info_path="contract_info.json"):
    # Load key + account
    pk = load_privkey()
    acct = Account.from_key(pk)
    print(f"🔑 Warden Address: {acct.address}")

    # Load contract info
    info = get_contract_info(info_path)
    source_info = info["source"]
    dest_info = info["destination"]

    # Connect networks
    w3_src = connect("source")
    w3_dst = connect("destination")

    source = w3_src.eth.contract(address=source_info["address"], abi=source_info["abi"])
    dest = w3_dst.eth.contract(address=dest_info["address"], abi=dest_info["abi"])

    # --------------------------
    # 1. Source → wrap (Deposit → Wrap)
    # --------------------------
    if chain == "source":
        print("=" * 50)
        print("🔍 CHECKING FOR DEPOSIT EVENTS → CALLING WRAP()")
        print("=" * 50)

        # Scan a very large range to catch all events
        latest_block = w3_src.eth.block_number
        from_block = max(latest_block - 20000, 0)  # Scan last 20,000 blocks
        print(f"📊 Block range: {from_block} to {latest_block} (total: {latest_block - from_block} blocks)")

        events = scan_blocks_for_events(w3_src, source_info["address"], from_block, latest_block, "Deposit")

        if not events:
            print("❌ No Deposit events found in scanned blocks.")
            return 1

        print(f"🎯 Processing {len(events)} Deposit events...")
        nonce = w3_dst.eth.get_transaction_count(acct.address)
        print(f"📝 Starting nonce on destination: {nonce}")

        success_count = 0
        for ev in events:
            token = ev["args"]["token"]
            recipient = ev["args"]["recipient"]
            amount = ev["args"]["amount"]

            print(f"➡️ Processing Deposit: token={token}, recipient={recipient}, amount={amount}")

            ok, nonce = send_tx(
                w3_dst, dest, "wrap",
                [token, recipient, amount],
                pk, nonce
            )

            if ok:
                print("🎉 Deposit → Wrap OK")
                success_count += 1
            else:
                print("❌ Deposit → Wrap FAILED")

        print(f"📈 Summary: {success_count}/{len(events)} Deposit events successfully bridged")
        return 1

    # --------------------------
    # 2. Destination → withdraw (Unwrap → Withdraw)
    # --------------------------
    if chain == "destination":
        print("=" * 50)
        print("🔍 CHECKING FOR UNWRAP EVENTS → CALLING WITHDRAW()")
        print("=" * 50)

        # Scan a very large range to catch all events
        latest_block = w3_dst.eth.block_number
        from_block = max(latest_block - 20000, 0)  # Scan last 20,000 blocks
        print(f"📊 Block range: {from_block} to {latest_block} (total: {latest_block - from_block} blocks)")

        events = scan_blocks_for_events(w3_dst, dest_info["address"], from_block, latest_block, "Unwrap")

        if not events:
            print("❌ No Unwrap events found in scanned blocks.")
            return 1

        print(f"🎯 Processing {len(events)} Unwrap events...")
        nonce = w3_src.eth.get_transaction_count(acct.address)
        print(f"📝 Starting nonce on source: {nonce}")

        success_count = 0
        for ev in events:
            token = ev["args"]["token"]
            recipient = ev["args"]["recipient"]
            amount = ev["args"]["amount"]

            print(f"➡️ Processing Unwrap: token={token}, recipient={recipient}, amount={amount}")

            ok, nonce = send_tx(
                w3_src, source, "withdraw",
                [token, recipient, amount],
                pk, nonce
            )

            if ok:
                print("🎉 Unwrap → Withdraw OK")
                success_count += 1
            else:
                print("❌ Unwrap → Withdraw FAILED")

        print(f"📈 Summary: {success_count}/{len(events)} Unwrap events successfully bridged")
        return 1

    return 1

# ----------------------
# Manual testing
# ----------------------
if __name__ == "__main__":
    print("🚀 Testing source → wrap")
    scan_blocks("source")

    print("\n🚀 Testing destination → withdraw")
    scan_blocks("destination")