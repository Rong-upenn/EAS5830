from web3 import Web3
from eth_account.messages import encode_defunct
import eth_account
import os
from eth_account import Account

def sign_message(challenge, keyId=0, filename="secret_key.txt"):
    """
    challenge - byte string
    filename - filename of the file that contains your account secret key
    To pass the tests, your signature must verify, and the account you use
    must have testnet funds on both the bsc and avalanche test networks.
    """
    # This code will read your "sk.txt" file
    # If the file is empty, it will raise an exception
    with open(filename, "r") as f:
        key = f.readlines()
    assert(len(key) > 0), "Your account secret_key.txt is empty"

    w3 = Web3()
    message = encode_defunct(challenge)

    # TODO recover your account information for your private key and sign the given challenge
    # Use the code from the signatures assignment to sign the given challenge
    # Step 1: Load existing private keys or create the file if it doesn’t exist
    if os.path.exists(filename):
        with open(filename, "r") as f:
            keys = f.read().splitlines()
    else:
        keys = []

    # Step 2: Check if private key for keyId exists; otherwise, generate and save a new one
    if keyId >= len(keys):
        # Generate a new account and save its private key
        new_account = Account.create()
        private_key = new_account.key.hex()
        keys.append(private_key)
        with open(filename, "a") as f:
            f.write(private_key + "\n")
    else:
        # Retrieve the private key for the specified keyId
        private_key = keys[keyId]

    # Step 3: Create account from private key
    acct = Account.from_key(private_key)
    eth_addr = acct.address

    # Step 4: Sign the message
    sig = acct.sign_message(message)





    assert eth_account.Account.recover_message(message,signature=sig.signature) == eth_addr, f"Failed to sign message properly"

    #return signed_message, account associated with the private key
    return sig, eth_addr


if __name__ == "__main__":
    for i in range(4):
        challenge = os.urandom(64)
        sig, addr= sign_message(challenge=challenge)
        print( addr )
