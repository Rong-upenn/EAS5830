import json
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.providers.rpc import HTTPProvider

'''
If you use one of the suggested infrastructure providers, the url will be of the form
now_url  = f"https://eth.nownodes.io/{now_token}"
alchemy_url = f"https://eth-mainnet.alchemyapi.io/v2/{alchemy_token}"
infura_url = f"https://mainnet.infura.io/v3/{infura_token}"
'''

def connect_to_eth():
	url = ""  # FILL THIS IN
	w3 = Web3(HTTPProvider(url))
	assert w3.is_connected(), f"Failed to connect to provider at {url}"
	return w3


def connect_with_middleware(contract_json):
	with open(contract_json, "r") as f:
		d = json.load(f)
		d = d['bsc']
		address = d['address']
		abi = d['abi']

	# TODO complete this method
	# The first section will be the same as "connect_to_eth()" but with a BNB url

	# Use your BNB testnet provider URL
	bsc_testnet_url = "https://data-seed-prebsc-1-s1.binance.org:8545/"  # BNB testnet URL
  w3 = Web3(HTTPProvider(bsc_testnet_url))

  # Inject middleware for BNB PoA consensus mechanism
  w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)

  # Assert the connection to BNB testnet
  assert w3.is_connected(), f"Failed to connect to provider at {url}"
  print("Successfully connected to BNB Testnet!")

  # Create a contract object using the ABI and contract address
  contract = w3.eth.contract(address=address, abi=abi)

	return w3, contract


if __name__ == "__main__":
 # Connect to Ethereum Mainnet
  w3_eth = connect_to_eth()

  # Connect to BNB Testnet and contract
  w3_bnb, contract = connect_with_middleware("contract_info.json")
  print(f"BNB Testnet contract address: {contract.address}")