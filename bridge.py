# bridge.py – FINAL AUTOGRADER-COMPATIBLE VERSION
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
import json
import time

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
    priv = "3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"  # <<<<<< PUT YOUR PRIVATE KEY HERE
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
# Event-driven bridge logic
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

        # Get recent blocks (last 200 blocks to be safe)
        latest_block = w3_src.eth.block_number
        from_block = max(0, latest_block - 200)
        
        # Use the older compatible method for event filtering
        try:
            # Try the newer method first
            events = source.events.Deposit.get_logs(fromBlock=from_block, toBlock='latest')
        except TypeError:
            # Fallback to manual block-by-block scanning
            print("⚠️ Using fallback event scanning method")
            events = []
            for block_num in range(from_block, latest_block + 1):
                try:
                    block_events = source.events.Deposit.get_logs(fromBlock=block_num, toBlock=block_num)
                    events.extend(block_events)
                except Exception as e:
                    print(f"⚠️ Could not scan block {block_num}: {e}")
                    continue

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

        # Get recent blocks (last 200 blocks to be safe)
        latest_block = w3_dst.eth.block_number
        from_block = max(0, latest_block - 200)
        
        # Use the older compatible method for event filtering
        try:
            # Try the newer method first
            events = dest.events.Unwrap.get_logs(fromBlock=from_block, toBlock='latest')
        except TypeError:
            # Fallback to manual block-by-block scanning
            print("⚠️ Using fallback event scanning method")
            events = []
            for block_num in range(from_block, latest_block + 1):
                try:
                    block_events = dest.events.Unwrap.get_logs(fromBlock=block_num, toBlock=block_num)
                    events.extend(block_events)
                except Exception as e:
                    print(f"⚠️ Could not scan block {block_num}: {e}")
                    continue

        if not events:
            print("ℹ️ No Unwrap events found.")
            return 1

        nonce = w3_src.eth.get_transaction_count(acct.address)

        for ev in events:
            # Note: Unwrap event uses different field names based on the ABI
            token = ev["args"]["underlying_token"]
            recipient = ev["args"]["to"]
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