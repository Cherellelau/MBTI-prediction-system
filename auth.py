import os
import hashlib
import hmac

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    pw = password.encode("utf-8")
    dk = hashlib.pbkdf2_hmac("sha256", pw, salt, 150_000)
    return salt.hex() + "$" + dk.hex()

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        pw = password.encode("utf-8")
        dk = hashlib.pbkdf2_hmac("sha256", pw, salt, 150_000).hex()
        return hmac.compare_digest(dk, dk_hex)
    except Exception:
        return False
