#!/usr/bin/env python3
import json
from pathlib import Path

from web3 import Web3
from web3.middleware.proof_of_authority import ExtraDataToPOAMiddleware
from eth_account import Account

# --------------------------------------------------------------------
# RPC endpoints & chain IDs (from assignment spec)
# --------------------------------------------------------------------
AVALANCHE_RPC = "https://api.avax-test.network/ext/bc/C/rpc"   # Fuji C-chain
BSC_RPC       = "https://data-seed-prebsc-1-s1.binance.org:8545/"

AVALANCHE_CHAIN_ID = 43113
BSC_CHAIN_ID       = 97

# How far back from the latest block we scan for events
FROM_BLOCK_WINDOW = 5000

# --------------------------------------------------------------------
# IMPORTANT: put your *warden* private key here (the deployer address
# that the graders are minting to and that has the correct roles).
# DO NOT commit the real key to GitHub.
# --------------------------------------------------------------------
WARDEN_PRIVATE_KEY = "0x3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"


def load_contracts():
    """
    Load contract_info.json and construct Web3 contract objects for
    the source (Avalanche) and destination (BSC) bridge contracts.
    """
    here = Path(__file__).resolve().parent
    with open(here / "contract_info.json", "r") as f:
        info = json.load(f)

    # Connect to the two chains
    w3_source = Web3(Web3.HTTPProvider(AVALANCHE_RPC))
    w3_dest = Web3(Web3.HTTPProvider(BSC_RPC))

    # Both networks are PoA-style, so inject the POA middleware
    w3_source.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    w3_dest.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    if not w3_source.is_connected():
        raise RuntimeError("Could not connect to Avalanche RPC")
    if not w3_dest.is_connected():
        raise RuntimeError("Could not connect to BSC RPC")

    source_addr = Web3.to_checksum_address(info["source"]["address"])
    dest_addr   = Web3.to_checksum_address(info["destination"]["address"])

    source_contract = w3_source.eth.contract(
        address=source_addr,
        abi=info["source"]["abi"],
    )
    dest_contract = w3_dest.eth.contract(
        address=dest_addr,
        abi=info["destination"]["abi"],
    )

    return w3_source, w3_dest, source_contract, dest_contract


def scan_deposits_and_wrap(
    w3_source, w3_dest, source_contract, dest_contract, private_key
):
    """
    Look for recent Deposit events on the source chain (Avalanche)
    and, for each one, call wrap() on the destination chain (BSC).

    Deposit(token, recipient, amount)  -->  dest.wrap(token, recipient, amount)
    """
    acct = Account.from_key(private_key)
    latest_block = w3_source.eth.block_number
    from_block = max(latest_block - FROM_BLOCK_WINDOW, 0)

    print(f"Scanning source chain for Deposit events from block {from_block} to {latest_block}...")

    deposit_events = source_contract.events.Deposit.get_logs(
        fromBlock=from_block,
        toBlock="latest",
    )

    if not deposit_events:
        print("No recent Deposit events found on source chain.")
        return

    print(f"Found {len(deposit_events)} Deposit event(s) on source chain.")

    # Start from current nonce on destination chain
    nonce = w3_dest.eth.get_transaction_count(acct.address)

    for ev in deposit_events:
        token     = ev["args"]["token"]
        recipient = ev["args"]["recipient"]
        amount    = ev["args"]["amount"]

        print(
            f"Bridging Deposit -> wrap(): "
            f"token={token}, recipient={recipient}, amount={amount}"
        )

        tx = dest_contract.functions.wrap(
            Web3.to_checksum_address(token),
            Web3.to_checksum_address(recipient),
            amount,
        ).build_transaction(
            {
                "from": acct.address,
                "chainId": BSC_CHAIN_ID,
                "nonce": nonce,
                "gas": 300_000,
                "gasPrice": w3_dest.eth.gas_price,
            }
        )
        nonce += 1

        signed = w3_dest.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = w3_dest.eth.send_raw_transaction(signed.rawTransaction)
        receipt = w3_dest.eth.wait_for_transaction_receipt(tx_hash)

        print(f"wrap() tx mined on destination: {tx_hash.hex()} (status={receipt.status})")


def scan_unwraps_and_withdraw(
    w3_source, w3_dest, source_contract, dest_contract, private_key
):
    """
    Look for recent Unwrap events on the destination chain (BSC)
    and, for each one, call withdraw() on the source chain (Avalanche).

    Unwrap(underlying_token, wrapped_token, frm, to, amount)
        --> source.withdraw(underlying_token, to, amount)
    """
    acct = Account.from_key(private_key)
    latest_block = w3_dest.eth.block_number
    from_block = max(latest_block - FROM_BLOCK_WINDOW, 0)

    print(f"Scanning destination chain for Unwrap events from block {from_block} to {latest_block}...")

    unwrap_events = dest_contract.events.Unwrap.get_logs(
        fromBlock=from_block,
        toBlock="latest",
    )

    if not unwrap_events:
        print("No recent Unwrap events found on destination chain.")
        return

    print(f"Found {len(unwrap_events)} Unwrap event(s) on destination chain.")

    # Start from current nonce on source chain
    nonce = w3_source.eth.get_transaction_count(acct.address)

    for ev in unwrap_events:
        underlying_token = ev["args"]["underlying_token"]
        to_addr          = ev["args"]["to"]
        amount           = ev["args"]["amount"]

        print(
            "Bridging Unwrap -> withdraw(): "
            f"underlying_token={underlying_token}, to={to_addr}, amount={amount}"
        )

        tx = source_contract.functions.withdraw(
            Web3.to_checksum_address(underlying_token),
            Web3.to_checksum_address(to_addr),
            amount,
        ).build_transaction(
            {
                "from": acct.address,
                "chainId": AVALANCHE_CHAIN_ID,
                "nonce": nonce,
                "gas": 300_000,
                "gasPrice": w3_source.eth.gas_price,
            }
        )
        nonce += 1

        signed = w3_source.eth.account.sign_transaction(tx, private_key=private_key)
        tx_hash = w3_source.eth.send_raw_transaction(signed.rawTransaction)
        receipt = w3_source.eth.wait_for_transaction_receipt(tx_hash)

        print(f"withdraw() tx mined on source: {tx_hash.hex()} (status={receipt.status})")


def main():
    if WARDEN_PRIVATE_KEY == "0xYOUR_PRIVATE_KEY_HERE":
        raise RuntimeError(
            "Please set WARDEN_PRIVATE_KEY in bridge.py to your warden's private key "
            "(the deployer used in earlier assignments)."
        )

    w3_source, w3_dest, source_contract, dest_contract = load_contracts()

    # 1. Source → Destination: Deposit event triggers wrap()
    scan_deposits_and_wrap(
        w3_source,
        w3_dest,
        source_contract,
        dest_contract,
        WARDEN_PRIVATE_KEY,
    )

    # 2. Destination → Source: Unwrap event triggers withdraw()
    scan_unwraps_and_withdraw(
        w3_source,
        w3_dest,
        source_contract,
        dest_contract,
        WARDEN_PRIVATE_KEY,
    )


if __name__ == "__main__":
    main()
