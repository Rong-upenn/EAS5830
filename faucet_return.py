#!/usr/bin/env python3
from web3 import Web3
import eth_account


def faucet_return():
    # YOUR ACCOUNT SECRET KEY AND MAXIMUM TRANSFER AMOUNT
    """The actual transfer amounts will be the value you set here or the
    maximum available in your accounts, whichever is less"""
    
    sk = "0x3725983718607fcf85308c2fcae6315ee0012b7e9a6655595fa7618b7473d8ef"  # Your secret key
    avax_max = 1000  # Max AVAX to transfer
    bnb_max = 1000  # Max BNB to transfer

    # Setup student account info
    try:
        from_acct = eth_account.Account.from_key(sk)
    except Exception as e:
        print(f"{e}\n{sk}\nThere was an error with your provided secret key")
        exit(1)

    # The course account address
    course_address = Web3.to_checksum_address("0x793A37a85964D96ACD6368777c7C7050F05b11dE")

    # Get a dict of Web3 instances for chains
    w3_dict = setup_web3_dict(avax_max, bnb_max)

    # Connect to requested web3 instances
    connect_to_apis(w3_dict)

    # Calculate transfer amount
    calculate_transfer(w3_dict, from_acct.address, course_address)

    # Transfer tokens
    for chain in w3_dict.keys():
        # Skip 0 balance accounts
        if w3_dict[chain]['transfer_amt'] <= 0:
            print(f"skipped {chain}, no transfer requested "
                  f"or no funds available to transfer")
            continue
        try:
            print(f"\nFor {chain}")
            txn_id = send_tokens(w3_dict[chain], from_acct, course_address)
            print(f"Amount sent:\t {w3_dict[chain]['transfer_amt']}\n"
                  f"Transaction ID:\t {txn_id}\n\nThank you for supporting "
                  f"the course account!")
        except Exception as e:
            print(f"The transfer failed:\n{e}\nPlease make corrections and try again")


def connect_to_apis(apis_dict):
    """ Connects to each network in the apis_dict and add w3 instance
    to "apis_dict" with the key "w3"
    """

    for api in apis_dict.keys():
        try:
            w3 = Web3(Web3.HTTPProvider(apis_dict[api]['block_api']))
            # Test to let you know you are connected to the network
            print(f"Latest {api} Testnet block number: ", w3.eth.block_number)
            apis_dict[api]["w3"] = w3
        except Exception as e:
            print(f"Connection to {api} was unsuccessful\n{e}\nPlease wait a minute and try again.")
            exit(1)


def setup_web3_dict(avax_max, bnb_max):
    """ Setup web3 dict for supported networks that returns
    a dict of apis and block explorers
    """
    new_dict = {"AVAX": {},
                "BNB": {}
                }

    new_dict["AVAX"]["block_api"] = "https://api.avax-test.network/ext/bc/C/rpc"
    new_dict["AVAX"]["block_explorer"] = "https://testnet.snowtrace.io/address/"
    new_dict["AVAX"]["transfer_amt"] = avax_max

    new_dict["BNB"]["block_api"] = "https://bsc-testnet.nodereal.io/v1/e9a36765eb8a40b9bd12e680a1fd2bc5"
    new_dict["BNB"]["block_explorer"] = "https://testnet.bscscan.com/address/"
    new_dict["BNB"]["transfer_amt"] = bnb_max

    return new_dict


def calculate_transfer(w3_dict, from_address, to_address):
    """ Calculate the max transferrable from each account and returns the
    lessor of avax/bnb_max or the max transferrable as transfer amount
    """
    for key in w3_dict.keys():
        chain = w3_dict[key]
        w3 = chain["w3"]
        transfer_max = chain["transfer_amt"]
        # Max units willing to pay (eth transfer is 21000 units)
        gas_limit = w3.eth.estimate_gas({'from': from_address, 'to': to_address})
        # Price willing to pay per unit in gwei
        gas_price = w3.eth.gas_price
        # Total transaction fee for transfer
        tx_fee = gas_price * gas_limit

        # From account balance in gwei
        balance = w3.eth.get_balance(from_address, "latest")
        # Calculate max transfer amount in Eth
        transfer_amt = (balance - tx_fee)/10**18
        transfer_amt = min(transfer_amt, transfer_max)

        # Update w3_dict
        chain["transfer_amt"] = transfer_amt
        chain["gas"] = gas_limit
        chain["gasPrice"] = gas_price


def send_tokens(chain_dict, from_acct, receiver_address):
    """ Builds, signs, and sends transactions using the provided inputs.
    """
    w3 = chain_dict['w3']
    # Build the transaction object
    transaction = {
        'nonce': w3.eth.get_transaction_count(from_acct.address),
        'to': receiver_address,
        'value': w3.to_wei(chain_dict['transfer_amt'], 'ether'),  # value to send
        'gas': chain_dict['gas'],
        'gasPrice': chain_dict['gasPrice'],
        'chainId': w3.eth.chain_id
    }

    # Sign the transaction
    signed_tx = w3.eth.account.sign_transaction(transaction, from_acct.key)
    print(f'Signed Txn:\t\t {signed_tx}')

    # Send the transaction
    w3.eth.send_raw_transaction(signed_tx.raw_transaction)  # Throws exception caught in main

    tx_receipt = w3.eth.wait_for_transaction_receipt(signed_tx.hash)
    if tx_receipt.status:
        print(f"Transaction confirmed at block {tx_receipt.blockNumber}")
    else:
        raise Exception("The transaction did not execute properly, no confirmation returned")

    return signed_tx.hash.hex()


if __name__ == '__main__':
    faucet_return()
