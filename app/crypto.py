import base64
import hashlib
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from app.config import SECRET_KEY

def _get_key():
    return hashlib.sha256(SECRET_KEY.encode('utf-8')).digest()

def encrypt_val(plain_text: str) -> str:
    if not plain_text:
        return ""
    key = _get_key()
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CFB, iv=iv)
    ciphertext = cipher.encrypt(plain_text.encode('utf-8'))
    return base64.b64encode(iv + ciphertext).decode('utf-8')

def decrypt_val(cipher_text_b64: str) -> str:
    if not cipher_text_b64:
        return ""
    try:
        raw = base64.b64decode(cipher_text_b64.encode('utf-8'))
        if len(raw) <= 16:
            return ""
        iv = raw[:16]
        ciphertext = raw[16:]
        key = _get_key()
        cipher = AES.new(key, AES.MODE_CFB, iv=iv)
        decrypted = cipher.decrypt(ciphertext)
        return decrypted.decode('utf-8')
    except Exception:
        return ""
