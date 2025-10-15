import requests
import json

# Pinata credentials
PINATA_API_KEY = "dca4709eece1079212c4"
PINATA_SECRET_API_KEY = "5a284d40769460da535f4443f9a0ed7ee3f4b376604fb62bbdaf362a1701fcd5"
PINATA_JSON_URL = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
PINATA_GATEWAY = "https://gateway.pinata.cloud/ipfs/"

def pin_to_ipfs(data):
    assert isinstance(data, dict), "Error pin_to_ipfs expects a dictionary"

    headers = {
        "Content-Type": "application/json",
        "pinata_api_key": PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_SECRET_API_KEY,
    }
    # pinJSONToIPFS requires {"pinataContent": <your dict>, ...}
    payload = {
        "pinataContent": data,
        "pinataOptions": {"cidVersion": 1}
    }

    try:
        resp = requests.post(PINATA_JSON_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        cid = resp.json().get("IpfsHash")
        if not cid:
            raise RuntimeError("Pinata response missing 'IpfsHash'")
        return cid
    except Exception as e:
        raise Exception(f"Failed to pin to IPFS: {e}")

def get_from_ipfs(cid, content_type="json"):
    assert isinstance(cid, str), "get_from_ipfs accepts a cid in the form of a string"

    url = f"{PINATA_GATEWAY}{cid}"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        # Assignment assumes JSON content
        data = resp.json() if content_type == "json" else json.loads(resp.text)
    except Exception as e:
        raise Exception(f"Failed to retrieve from IPFS: {e}")

    assert isinstance(data, dict), "get_from_ipfs should return a dict"
    return data

if __name__ == "__main__":
    # Simple sanity test (will succeed if your keys are valid)
    test_data = {"name": "Alice", "age": 15, "city": "Wonderland"}
    try:
        cid = pin_to_ipfs(test_data)
        print(f"Pinned CID: {cid}")
        print("Fetched:", get_from_ipfs(cid))
    except Exception as e:
        print("Error:", e)
