# bridge.py - FINAL VERSION FOR AUTOGRADER
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
# Manual event scanning for Unwrap events
# ----------------------
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

def get_events_manual(w3, contract_address, from_block, to_block):
    """Get all events manually by scanning blocks"""
    events = []
    for block_num in range(from_block, to_block + 1):
        try:
            block = w3.eth.get_block(block_num, full_transactions=True)
            for tx in block.transactions:
                if isinstance(tx, dict) and tx.get('to') and tx['to'].lower() == contract_address.lower():
                    try:
                        receipt = w3.eth.get_transaction_receipt(tx['hash'])
                        for log in receipt.logs:
                            if log['address'].lower() == contract_address.lower():
                                events.append({
                                    'blockNumber': block_num,
                                    'log': log
                                })
                    except:
                        continue
        except:
            continue
    return events

# ----------------------
# Event-driven bridge logic - MAIN FUNCTION AUTOGRADER CALLS
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
        print("🔍 Checking for Deposit events → sending wrap() ...")

        # Get recent blocks
        latest_block = w3_src.eth.block_number
        from_block = max(latest_block - 1000, 0)

        try:
            # Try standard method first
            events = source.events.Deposit().get_logs(fromBlock=from_block, toBlock=latest_block)
        except:
            # Fallback to manual scanning
            print("⚠️ Using manual event scanning")
            all_events = get_events_manual(w3_src, source_info["address"], from_block, latest_block)
            events = []
            for event in all_events:
                log = event['log']
                if len(log['topics']) > 0:
                    deposit_sig = "0x5548c837ab068cf56a2c2479df0882a4922fd203edb7517321831d95078c5f62"
                    if log['topics'][0].hex() == deposit_sig and len(log['topics']) == 3:
                        token = Web3.to_checksum_address(log['topics'][1][12:].hex())
                        recipient = Web3.to_checksum_address(log['topics'][2][12:].hex())
                        amount = int(log['data'], 16) if log['data'] != '0x' else 0
                        events.append({
                            'args': {
                                'token': token,
                                'recipient': recipient,
                                'amount': amount
                            }
                        })

        if not events:
            print("ℹ️ No Deposit events found.")
            return 1

        nonce = w3_dst.eth.get_transaction_count(acct.address)

        for ev in events:
            token = ev["args"]["token"]
            recipient = ev["args"]["recipient"]
            amount = ev["args"]["amount"]

            print(f"➡️ Deposit detected: token={token}, recipient={recipient}, amount={amount}")

            ok, nonce = send_tx(
                w3_dst, dest, "wrap",
                [token, recipient, amount],
                pk, nonce
            )

            if ok:
                print("🎉 Deposit → Wrap OK")
            else:
                print("❌ Deposit → Wrap FAILED")

        return 1

    # --------------------------
    # 2. Destination → withdraw (Unwrap → Withdraw)
    # --------------------------
    if chain == "destination":
        print("🔍 Checking for Unwrap events → sending withdraw() ...")

        latest_block = w3_dst.eth.block_number
        from_block = max(latest_block - 1000, 0)

        # Use manual scanning for Unwrap events (due to signature mismatch)
        all_events = get_events_manual(w3_dst, dest_info["address"], from_block, latest_block)
        events = []
        for event in all_events:
            decoded = decode_unwrap_event(event['log'])
            if decoded:
                events.append(decoded)

        if not events:
            print("ℹ️ No Unwrap events found.")
            return 1

        nonce = w3_src.eth.get_transaction_count(acct.address)

        for ev in events:
            token = ev["args"]["token"]
            recipient = ev["args"]["recipient"]
            amount = ev["args"]["amount"]

            print(f"➡️ Unwrap detected: token={token}, recipient={recipient}, amount={amount}")

            ok, nonce = send_tx(
                w3_src, source, "withdraw",
                [token, recipient, amount],
                pk, nonce
            )

            if ok:
                print("🎉 Unwrap → Withdraw OK")
            else:
                print("❌ Unwrap → Withdraw FAILED")

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