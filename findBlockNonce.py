
import hashlib

def _count_trailing_zero_bits(x: int) -> int:
    """Return the number of trailing zero bits in the non-negative integer x."""
    if x == 0:
        # For our PoW use-case this effectively satisfies any k, but we won't rely on this.
        return 256  # SHA-256 bit length upper bound
    return (x & -x).bit_length() - 1

def mine_block(k: int, prev_hash: bytes, rand_lines: list[str]) -> bytes:
    """
    Brute-force a nonce so that SHA256(prev_hash + rand_lines + nonce) has at least k trailing zero bits.

    Args:
        k: integer difficulty (number of required trailing zero bits, i.e., LSBs)
        prev_hash: bytes, the previous block hash
        rand_lines: list[str], transactions in-order (strings)

    Returns:
        nonce: bytes
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
    # Tiny self-test / demo: DO NOT use large k here, or it'll take very long.
    import sys, time
    k = 11 if len(sys.argv) < 2 else int(sys.argv[1])
    prev_hash = hashlib.sha256(b"genesis").digest()
    rand_lines = ["hello", "world", "transaction-1", "transaction-2"]
    print(f"Mining demo block with k={k} ...")
    t0 = time.time()
    nonce = mine_block(k, prev_hash, rand_lines)
    dt = time.time() - t0
    ok = verify_nonce(k, prev_hash, rand_lines, nonce)
    print(f"Found nonce: {nonce.hex()}  (len={len(nonce)} bytes)")
    print(f"Verify: {ok}")
    print(f"Elapsed: {dt:.3f}s")
