# bridge.py
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
import json

AVAX_RPC = "https://api.avax-test.network/ext/bc/C/rpc"
BSC_RPC  = "https://data-seed-prebsc-1-s1.binance.org:8545/"
FROM_BLOCK_WINDOW = 5000

# --------------------------------------------------------------------
# Replace with your warden private key (must include 0x)
# --------------------------------------------------------------------
WARDEN_PRIVATE_KEY = "0x3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"


# ---------------- Utility Functions ---------------- #

def _fix_addr(addr):
    """
    Normalize any address to checksummed 0x + last 40 hex chars.
    Handles bytes, hex, padded strings, etc.
    """
    if isinstance(addr, bytes):
        addr = addr.hex()

    addr = str(addr)

    if not addr.startswith("0x"):
        addr = "0x" + addr[-40:]

    return Web3.to_checksum_address(addr)


def _boosted_gas(w3):
    """Prevent replacement-transaction-underpriced errors."""
    return int(w3.eth.gas_price * 1.2)


def _nonce(w3, acct):
    """Always fetch fresh nonce to avoid 'nonce too low'."""
    return w3.eth.get_transaction_count(acct.address)


def topic(signature_text):
    """
    Produce a valid 0x-prefixed keccak hash for event filter topics.
    Fully compatible with old Web3 builds.
    """
    h = Web3.keccak(text=signature_text)
    hx = h.hex()
    if not hx.startswith("0x"):
        hx = "0x" + hx
    return hx.lower()


# ---------------- Setup ---------------- #

def _load():
    with open("contract_info.json", "r") as f:
        j = json.load(f)

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
        address=Web3.to_checksum_address(j["source"]["address"]),
        abi=j["source"]["abi"]
    )
    dst = w3d.eth.contract(
        address=Web3.to_checksum_address(j["destination"]["address"]),
        abi=j["destination"]["abi"]
    )

    return acct, w3s, w3d, src, dst


# ---------------- Event Handlers ---------------- #

def _scan_deposit(acct, w3s, w3d, src, dst):
    latest = w3s.eth.block_number
    MAX_RANGE = 2048
    from_block = max(latest - MAX_RANGE, 0)

    topic0 = topic("Deposit(address,address,uint256)")

    flt = w3s.eth.filter({
        "fromBlock": from_block,
        "toBlock": "latest",
        "address": src.address,
        "topics": [topic0],
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
            "from": acct.address,
            "nonce": nonce,
            "chainId": w3d.eth.chain_id,
            "gas": 300000,
            "gasPrice": _boosted_gas(w3d),
        })

        signed = w3d.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
        w3d.eth.send_raw_transaction(signed.rawTransaction)



def _scan_unwrap(acct, w3s, w3d, src, dst):
    latest = w3d.eth.block_number
    MAX_RANGE = 2048
    from_block = max(latest - MAX_RANGE, 0)

    topic0 = topic("Unwrap(address,address,address,address,uint256)")

    flt = w3d.eth.filter({
        "fromBlock": from_block,
        "toBlock": "latest",
        "address": dst.address,
        "topics": [topic0],
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
            "from": acct.address,
            "nonce": nonce,
            "chainId": w3s.eth.chain_id,
            "gas": 300000,
            "gasPrice": _boosted_gas(w3s),
        })

        signed = w3s.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
        w3s.eth.send_raw_transaction(signed.rawTransaction)



# ---------------- Grader Entry Point ---------------- #

def scan_blocks(*args, **kwargs):
    """
    Called by autograder.

    scan_blocks("source")      -> detect Deposit on Source, wrap() on Dest
    scan_blocks("destination") -> detect Unwrap on Dest, withdraw() on Source

    Extra args are ignored, but accepted for compatibility.
    """
    side = args[0] if args else None
    if not side:
        return

    if side not in ("source", "destination"):
        return

    acct, w3s, w3d, src, dst = _load()

    if side == "source":
        _scan_deposit(acct, w3s, w3d, src, dst)

    elif side == "destination":
        _scan_unwrap(acct, w3s, w3d, src, dst)
