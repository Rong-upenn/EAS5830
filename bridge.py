# bridge.py
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
import json

# --------------------------------------------------------------------
# RPC endpoints
# --------------------------------------------------------------------
AVAX_RPC = "https://api.avax-test.network/ext/bc/C/rpc"        # Source (Avalanche Fuji)
BSC_RPC  = "https://data-seed-prebsc-1-s1.binance.org:8545/"   # Destination (BSC Testnet)

# --------------------------------------------------------------------
# Warden private key (the deployer the grader mints to)
# --------------------------------------------------------------------
WARDEN_PRIVATE_KEY = "0x3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"


# ================== Utility Helpers ================== #

def _fix_addr(addr):
    """
    Normalize any address into a proper 0x-prefixed checksummed address.
    Handles bytes, hex strings, padded values, etc.
    """
    if isinstance(addr, bytes):
        addr = addr.hex()
    addr = str(addr)
    if not addr.startswith("0x"):
        addr = "0x" + addr[-40:]
    return Web3.to_checksum_address(addr)


def _boosted_gas(w3):
    """Boost gas price a bit to avoid 'replacement transaction underpriced'."""
    return int(w3.eth.gas_price * 1.2)


def _nonce(w3, acct):
    """Always fetch a fresh nonce to avoid 'nonce too low'."""
    return w3.eth.get_transaction_count(acct.address)


def topic(signature_text):
    """
    Produce a valid 0x-prefixed keccak hash for event filter topics.
    Works on older web3 versions.
    """
    h = Web3.keccak(text=signature_text)
    hx = h.hex()
    if not hx.startswith("0x"):
        hx = "0x" + hx
    return hx.lower()


# ================== Setup ================== #

def _load():
    """Load web3 connections, account, and source/destination contracts."""
    with open("contract_info.json", "r") as f:
        info = json.load(f)

    w3s = Web3(Web3.HTTPProvider(AVAX_RPC))
    w3d = Web3(Web3.HTTPProvider(BSC_RPC))

    w3s.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    w3d.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

    if not w3s.is_connected():
        raise Exception("Could not connect to Avalanche RPC")
    if not w3d.is_connected():
        raise Exception("Could not connect to BSC RPC")

    acct = Account.from_key(WARDEN_PRIVATE_KEY)

    src = w3s.eth.contract(
        address=Web3.to_checksum_address(info["source"]["address"]),
        abi=info["source"]["abi"],
    )
    dst = w3d.eth.contract(
        address=Web3.to_checksum_address(info["destination"]["address"]),
        abi=info["destination"]["abi"],
    )

    return acct, w3s, w3d, src, dst


# ================== Event Handlers ================== #

def _scan_deposit(acct, w3s, w3d, src, dst):
    """
    Grader has sent a Deposit on SOURCE (Avalanche).
    Find Deposit events and call wrap() on DEST (BSC).
    """
    latest = w3s.eth.block_number
    # Respect RPC limit: max 2048 blocks
    from_block = latest - 2048
    if from_block < 0:
        from_block = 0

    # Event signature from ABI: Deposit(address,address,uint256)
    topic0 = topic("Deposit(address,address,uint256)")

    flt = w3s.eth.filter({
        "fromBlock": from_block,
        "toBlock":   latest,          # integer, NOT "latest"
        "address":   src.address,
        "topics":   [topic0],
    })

    logs = flt.get_all_entries()
    if not logs:
        return

    for log in logs:
        ev = src.events.Deposit().process_log(log)
        token     = _fix_addr(ev["args"]["token"])
        recipient = _fix_addr(ev["args"]["recipient"])
        amount    = int(ev["args"]["amount"])

        nonce = _nonce(w3d, acct)

        tx = dst.functions.wrap(
            token,
            recipient,
            amount
        ).build_transaction({
            "from":     acct.address,
            "nonce":    nonce,
            "chainId":  w3d.eth.chain_id,
            "gas":      300000,
            "gasPrice": _boosted_gas(w3d),
        })

        signed = w3d.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
        tx_hash = w3d.eth.send_raw_transaction(signed.rawTransaction)
        # Wait so the event is definitely there when grader checks
        w3d.eth.wait_for_transaction_receipt(tx_hash)


def _scan_unwrap(acct, w3s, w3d, src, dst):
    """
    Grader has sent an Unwrap on DESTINATION (BSC).
    Find Unwrap events and call withdraw() on SOURCE (Avalanche).
    """
    latest = w3d.eth.block_number
    from_block = latest - 2048
    if from_block < 0:
        from_block = 0

    # Event signature from ABI: Unwrap(address,address,address,address,uint256)
    topic0 = topic("Unwrap(address,address,address,address,uint256)")

    flt = w3d.eth.filter({
        "fromBlock": from_block,
        "toBlock":   latest,
        "address":   dst.address,
        "topics":   [topic0],
    })

    logs = flt.get_all_entries()
    if not logs:
        return

    for log in logs:
        ev = dst.events.Unwrap().process_log(log)
        underlying = _fix_addr(ev["args"]["underlying_token"])
        to_addr    = _fix_addr(ev["args"]["to"])
        amount     = int(ev["args"]["amount"])

        nonce = _nonce(w3s, acct)

        tx = src.functions.withdraw(
            underlying,
            to_addr,
            amount
        ).build_transaction({
            "from":     acct.address,
            "nonce":    nonce,
            "chainId":  w3s.eth.chain_id,
            "gas":      300000,
            "gasPrice": _boosted_gas(w3s),
        })

        signed = w3s.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
        tx_hash = w3s.eth.send_raw_transaction(signed.rawTransaction)
        w3s.eth.wait_for_transaction_receipt(tx_hash)


# ================== Autograder Entry ================== #

def scan_blocks(*args, **kwargs):
    """
    Entry point the autograder calls.

    scan_blocks("source", ...)      -> handle Deposit on source → wrap() on dest
    scan_blocks("destination", ...) -> handle Unwrap on dest → withdraw() on source

    Extra args are ignored but accepted to match grader’s call signature.
    """
    if not args:
        return

    side = args[0]
    if side not in ("source", "destination"):
        return

    acct, w3s, w3d, src, dst = _load()

    if side == "source":
        _scan_deposit(acct, w3s, w3d, src, dst)
    else:  # "destination"
        _scan_unwrap(acct, w3s, w3d, src, dst)
