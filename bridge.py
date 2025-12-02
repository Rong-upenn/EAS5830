# bridge.py
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account import Account
import json

AVAX_RPC = "https://api.avax-test.network/ext/bc/C/rpc"
BSC_RPC  = "https://data-seed-prebsc-1-s1.binance.org:8545/"

FROM_BLOCK_WINDOW = 5000

WARDEN_PRIVATE_KEY = "0x3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"  # <-- replace me


def _load():
    with open("contract_info.json", "r") as f:
        j = json.load(f)

    w3s = Web3(Web3.HTTPProvider(AVAX_RPC))
    w3d = Web3(Web3.HTTPProvider(BSC_RPC))

    w3s.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    w3d.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

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


def _scan_deposit(acct, w3s, w3d, src, dst):
    latest = w3s.eth.block_number
    from_block = max(latest - FROM_BLOCK_WINDOW, 0)

    # topic0 = keccak("Deposit(address,address,uint256)")
    sig = Web3.keccak(text="Deposit(address,address,uint256)").hex()

    flt = w3s.eth.filter({
        "fromBlock": from_block,
        "toBlock": "latest",
        "address": src.address,
        "topics": [sig],
    })

    logs = flt.get_all_entries()
    if not logs:
        return

    nonce = w3d.eth.get_transaction_count(acct.address)

    for log in logs:
        ev = src.events.Deposit().process_log(log)
        token     = ev["args"]["token"]
        recipient = ev["args"]["recipient"]
        amount    = ev["args"]["amount"]

        tx = dst.functions.wrap(
            Web3.to_checksum_address(token),
            Web3.to_checksum_address(recipient),
            amount
        ).build_transaction({
            "from": acct.address,
            "nonce": nonce,
            "chainId": w3d.eth.chain_id,
            "gas": 300000,
            "gasPrice": w3d.eth.gas_price,
        })
        nonce += 1

        signed = w3d.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
        w3d.eth.send_raw_transaction(signed.rawTransaction)


def _scan_unwrap(acct, w3s, w3d, src, dst):
    latest = w3d.eth.block_number
    from_block = max(latest - FROM_BLOCK_WINDOW, 0)

    # topic0 = keccak("Unwrap(address,address,address,address,uint256)")
    sig = Web3.keccak(text="Unwrap(address,address,address,address,uint256)").hex()

    flt = w3d.eth.filter({
        "fromBlock": from_block,
        "toBlock": "latest",
        "address": dst.address,
        "topics": [sig],
    })

    logs = flt.get_all_entries()
    if not logs:
        return

    nonce = w3s.eth.get_transaction_count(acct.address)

    for log in logs:
        ev = dst.events.Unwrap().process_log(log)
        underlying = ev["args"]["underlying_token"]
        to_addr    = ev["args"]["to"]
        amount     = ev["args"]["amount"]

        tx = src.functions.withdraw(
            Web3.to_checksum_address(underlying),
            Web3.to_checksum_address(to_addr),
            amount
        ).build_transaction({
            "from": acct.address,
            "nonce": nonce,
            "chainId": w3s.eth.chain_id,
            "gas": 300000,
            "gasPrice": w3s.eth.gas_price,
        })
        nonce += 1

        signed = w3s.eth.account.sign_transaction(tx, WARDEN_PRIVATE_KEY)
        w3s.eth.send_raw_transaction(signed.rawTransaction)


# ====================================================================
# REQUIRED BY AUTOGRADER
# ====================================================================
def scan_blocks(*args, **kwargs):
    if not args:
        return
    which = args[0]

    acct, w3s, w3d, src, dst = _load()

    if which == "source":
        _scan_deposit(acct, w3s, w3d, src, dst)
    elif which == "destination":
        _scan_unwrap(acct, w3s, w3d, src, dst)
    else:
        raise ValueError("scan_blocks requires 'source' or 'destination'")
