# test_unwrap_decoding.py
from web3 import Web3

def test_unwrap_decoding():
    print("=== TESTING UNWRAP DECODING ===")
    
    # Test data from the actual logs
    test_data_1 = bytes.fromhex("000000000000000000000000c677c31ad31f73a5290f5ef067f8cef8d301e45c00000000000000000000000091b98809cc8aac8f4db6d2f2ded68a6dcdb729da0000000000000000000000000000000000000000000000000000000000000117")
    test_data_2 = bytes.fromhex("0000000000000000000000000773b81e0524447784cce1f3808fed6aaa156ec800000000000000000000000091b98809cc8aac8f4db6d2f2ded68a6dcdb729da0000000000000000000000000000000000000000000000000000000000000275")
    
    def decode_data(data):
        token_bytes = data[0:32]
        recipient_bytes = data[32:64] 
        amount_bytes = data[64:96]
        
        token = Web3.to_checksum_address(token_bytes[12:].hex())
        recipient = Web3.to_checksum_address(recipient_bytes[12:].hex())
        amount = int.from_bytes(amount_bytes, 'big')
        
        return token, recipient, amount
    
    print("Test data 1:")
    token1, recipient1, amount1 = decode_data(test_data_1)
    print(f"  Token: {token1}")
    print(f"  Recipient: {recipient1}")
    print(f"  Amount: {amount1}")
    
    print("\nTest data 2:")
    token2, recipient2, amount2 = decode_data(test_data_2)
    print(f"  Token: {token2}")
    print(f"  Recipient: {recipient2}")
    print(f"  Amount: {amount2}")

if __name__ == "__main__":
    test_unwrap_decoding()