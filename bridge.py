# bridge.py – final version for EAS5830 Bridge V
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
import json


# -------------------------
# RPC connections
# -------------------------
def connect_to(chain: str) -> Web3:
    """
    Connect to AVAX Fuji (source) or BSC Testnet (destination).
    """
    if chain == "source":  # Avalanche Fuji
        rpc_url = "https://endpoints.omniatech.io/v1/avax/fuji/public"
    elif chain == "destination":  # BSC Testnet
        rpc_url = "https://bsc-testnet-rpc.publicnode.com"
    else:
        raise ValueError(f"Unknown chain: {chain}")

    w3 = Web3(Web3.HTTPProvider(rpc_url))
    # Required for these PoA-style testnets
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    if not w3.is_connected():
        raise RuntimeError(f"Failed to connect to RPC for {chain}")

    return w3


# -------------------------
# Contract info
# -------------------------
def get_contract_info(chain: str, path: str = "contract_info.json"):
    """
    Load address + ABI for 'source' or 'destination' from contract_info.json
    """
    with open(path, "r") as f:
        data = json.load(f)
    return data[chain]


# -------------------------
# Private key
# -------------------------
def load_private_key() -> str:
    """
    Load the warden private key.
    IMPORTANT: fill in your actual private key string below.
    """
    priv_key = "3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"  # <<< PUT YOUR PRIVATE KEY HERE, e.g. "0xabc123..."

    if not priv_key:
        raise RuntimeError("Private key is empty in load_private_key().")

    if not priv_key.startswith("0x"):
        priv_key = "0x" + priv_key

    return priv_key


# -------------------------
# TX helper
# -------------------------
def sign_and_send_tx(
    w3: Web3,
    contract,
    function_name: str,
    args,
    priv_key: str,
    nonce: int,
    gas_limit: int = 200_000,
):
    """
    Sign and send a transaction to a contract function.
    Returns (success: bool, new_nonce: int)
    """
    acct = Account.from_key(priv_key)
    print(f"📝 Sending {function_name} with nonce={nonce}, gas={gas_limit}")

    try:
        fn = getattr(contract.functions, function_name)(*args)
        tx = fn.build_transaction(
            {
                "from": acct.address,
                "nonce": nonce,
                "chainId": w3.eth.chain_id,
                "gas": gas_limit,
                "gasPrice": w3.eth.gas_price,
            }
        )

        signed = w3.eth.account.sign_transaction(tx, priv_key)

        # Compatibility with eth-account versions
        raw_tx = getattr(signed, "rawTransaction", None)
        if raw_tx is None:
            raw_tx = getattr(signed, "raw_transaction")

        tx_hash = w3.eth.send_raw_transaction(raw_tx)
        print(f"➡️ Sent {function_name}: {tx_hash.hex()}")

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status == 1:
            print(f"✅ {function_name} succeeded in block {receipt.blockNumber}")
            return True, nonce + 1
        else:
            print(f"❌ {function_name} reverted")
            # Refresh nonce after failure
            new_nonce = w3.eth.get_transaction_count(acct.address)
            return False, new_nonce

    except Exception as e:
        print(f"❌ Error during {function_name}: {e}")
        new_nonce = w3.eth.get_transaction_count(acct.address)
        return False, new_nonce


# -------------------------
# Main bridge logic
# -------------------------
def scan_blocks(chain: str, contract_info: str = "contract_info.json") -> int:
    """
    Entry point called by autograder.

    chain == "source":
        - Read Deposit events on AVAX Source
        - For each Deposit(token, recipient, amount), call wrap(token, recipient, amount) on BSC Destination.

    chain == "destination":
        - Read Unwrap events on BSC Destination
        - For each Unwrap(token, recipient, amount), call withdraw(token, recipient, amount) on AVAX Source.
    """
    # Load key & account
    priv_key = load_private_key()
    warden = Account.from_key(priv_key)
    print(f"🔑 Warden Address: {warden.address}")

    # Load contract metadata
    src_info = get_contract_info("source", contract_info)
    dst_info = get_contract_info("destination", contract_info)

    # Connect to both chains
    w3_source = connect_to("source")
    w3_dest = connect_to("destination")

    # Instantiate contracts
    source_contract = w3_source.eth.contract(
        address=src_info["address"], abi=src_info["abi"]
    )
    dest_contract = w3_dest.eth.contract(
        address=dst_info["address"], abi=dst_info["abi"]
    )

    # ---------------------------------------------------
    # Case 1: Source side → handle Deposit → wrap()
    # ---------------------------------------------------
    if chain == "source":
        print("🔍 Checking for Deposit events → calling wrap() on destination...")

        latest_block = w3_source.eth.block_number
        from_block = max(latest_block - 200, 0)  # scan recent blocks

        try:
            # web3.py v6: get_logs(from_block=..., to_block=...)
            deposit_events = source_contract.events.Deposit.get_logs(
                from_block=from_block, to_block=latest_block
            )
        except Exception as e:
            print(f"❌ Error fetching Deposit logs: {e}")
            return 0

        if not deposit_events:
            print("ℹ️ No Deposit events found in recent blocks.")
            return 1

        # Use nonce on destination (BSC) for wrap() calls
        nonce = w3_dest.eth.get_transaction_count(warden.address)

        for ev in deposit_events:
            token = ev["args"]["token"]
            recipient = ev["args"]["recipient"]
            amount = ev["args"]["amount"]

            print(
                f"➡️ Detected Deposit: token={token}, recipient={recipient}, amount={amount}"
            )

            ok, nonce = sign_and_send_tx(
                w3_dest,
                dest_contract,
                "wrap",
                [token, recipient, amount],
                priv_key,
                nonce,
            )

            if ok:
                print("🎉 Bridged: Deposit → Wrap")
            else:
                print("❌ Failed bridging Deposit → Wrap")

        return 1

    # ---------------------------------------------------
    # Case 2: Destination side → handle Unwrap → withdraw()
    # ---------------------------------------------------
    if chain == "destination":
        print("🔍 Checking for Unwrap events → calling withdraw() on source...")

        latest_block = w3_dest.eth.block_number
        # BSC 节点很严格，窗口开小一点就够了
        from_block = max(latest_block - 20, 0)

        try:
            unwrap_events = dest_contract.events.Unwrap.get_logs(
                from_block=from_block, to_block=latest_block
            )
        except Exception as e:
            print(f"❌ Error fetching Unwrap logs: {e}")
            return 0


        if not unwrap_events:
            print("ℹ️ No Unwrap events found in recent blocks.")
            return 1

        # Use nonce on source (AVAX) for withdraw() calls
        nonce = w3_source.eth.get_transaction_count(warden.address)

        for ev in unwrap_events:
            token = ev["args"]["token"]
            recipient = ev["args"]["recipient"]
            amount = ev["args"]["amount"]

            print(
                f"➡️ Detected Unwrap: token={token}, recipient={recipient}, amount={amount}"
            )

            ok, nonce = sign_and_send_tx(
                w3_source,
                source_contract,
                "withdraw",
                [token, recipient, amount],
                priv_key,
                nonce,
            )

            if ok:
                print("🎉 Bridged: Unwrap → Withdraw")
            else:
                print("❌ Failed bridging Unwrap → Withdraw")

        return 1

    print(f"❌ Invalid chain argument to scan_blocks: {chain}")
    return 0


# -------------------------
# Local testing
# -------------------------
if __name__ == "__main__":
    print("🚀 Testing scan_blocks('source')")
    scan_blocks("source")

    print("\n🚀 Testing scan_blocks('destination')")
    scan_blocks("destination")
