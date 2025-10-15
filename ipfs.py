import requests
import json

# Pinata credentials
PINATA_API_KEY = "dca4709eece1079212c4"
PINATA_SECRET_API_KEY = "5a284d40769460da535f4443f9a0ed7ee3f4b376604fb62bbdaf362a1701fcd5"
PINATA_JSON_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
PINATA_GATEWAY = "https://gateway.pinata.cloud/ipfs/"

def pin_to_ipfs(data):
	assert isinstance(data,dict), f"Error pin_to_ipfs expects a dictionary"
	#YOUR CODE HERE

	# Convert dictionary to JSON string
	json_data = json.dumps(data)

	headers = {
        'pinata_api_key': PINATA_API_KEY,
        'pinata_secret_api_key': PINATA_SECRET_API_KEY,
    }

	# Pin JSON data to IPFS via Pinata
	response = requests.post(PINATA_JSON_URL, headers=headers, files={'file': ('data.json', json_data)})
	# Check for successful response
	if response.status_code == 200:
		cid = response.json()['IpfsHash'] # Extract CID from response
	else:
		raise Exception(f"Failed to pin to IPFS: {response.text}")

	return cid

def get_from_ipfs(cid,content_type="json"):
	assert isinstance(cid,str), f"get_from_ipfs accepts a cid in the form of a string"
	#YOUR CODE HERE	
	url = f"{PINATA_GATEWAY}{cid}"
	# Fetch data from IPFS via Pinata gateway
	response = requests.get(url)

	# Check for successful response
	if response.status_code == 200:
		data = json.loads(response.content)
		assert isinstance(data,dict), f"get_from_ipfs should return a dict"
		return data
	else:
		raise Exception(f"Failed to retrieve from IPFS: {response.text}")
	

	
if __name__ == "__main__":
	# Test pinning to IPFS via Pinata
	test_data = {"name": "Alice", "age": 15, "city": "Wonderland"}
	try:
		cid = pin_to_ipfs(test_data)
		print(f"Successfully pinned to IPFS with CID: {cid}")

		# Test retrieving from IPFS via Pinata gateway
		retrieved_data = get_from_ipfs(cid)
		print(f"Successfully retrieved from IPFS: {retrieved_data}")
	except Exception as e:
		print(f"Error: {e}")


		