
import hashlib

def _count_trailing_zero_bits(x: int) -> int:
    """Return the number of trailing zero bits in the non-negative integer x."""
    if x == 0:
        # For our PoW use-case this effectively satisfies any k, but we won't rely on this.
        return 256  # SHA-256 bit length upper bound
    return (x & -x).bit_length() - 1

def mine_block(k: int, prev_hash: bytes, rand_lines: list[str]) -> bytes:
    """
        k - Number of trailing zeros in the binary representation (integer)
        prev_hash - the hash of the previous block (bytes)
        rand_lines - a set of "transactions," i.e., data to be included in this block (list of strings)

        Complete this function to find a nonce such that 
        sha256( prev_hash + rand_lines + nonce )
        has k trailing zeros in its *binary* representation
    """
    assert isinstance(prev_hash, (bytes, bytearray)), "prev_hash must be bytes"
    assert isinstance(k, int) and k >= 0, "k must be a non-negative integer"
    # Prebuild constant prefix: prev_hash + all tx in order, encoded as UTF-8 bytes.
    prefix = prev_hash + b"".join(s.encode("utf-8") for s in rand_lines)

    # We'll iterate nonce as an unsigned 64-bit integer, encoded as 8-byte big-endian.
    # Any consistent encoding works, but fixed-length bytes are fast and simple.
    mask = (1 << k) - 1  # lower-k-bit mask; when (digest_int & mask) == 0, we have >= k trailing zeros.
    nonce_int = 0
    to_bytes = int.to_bytes

    while True:
        nonce = to_bytes(nonce_int, 8, "big")
        h = hashlib.sha256(prefix + nonce).digest()
        # Convert digest to int (big-endian) and test trailing zeros via mask
        if int.from_bytes(h, "big") & mask == 0:
            return nonce
        nonce_int += 1

# Optional convenience function for verifying a mined nonce.
def verify_nonce(k: int, prev_hash: bytes, rand_lines: list[str], nonce: bytes) -> bool:
    prefix = prev_hash + b"".join(s.encode("utf-8") for s in rand_lines)
    h = hashlib.sha256(prefix + nonce).digest()
    mask = (1 << k) - 1
    return int.from_bytes(h, "big") & mask == 0

if __name__ == "__main__":
   
    import sys, time
    # This code will be helpful for your testing
    filename = "bitcoin_text.txt"
    num_lines = 11

    # The "difficulty" level. For our blocks this is the number of Least Significant Bits
    # that are 0s. For example, if diff = 5 then the last 5 bits of a valid block hash would be zeros
    # The grader will not exceed 20 bits of "difficulty" because larger values take to long
    diff = 20

    transactions = get_random_lines(filename, num_lines)
    nonce = mine_block(diff, transactions)
    print(nonce)
