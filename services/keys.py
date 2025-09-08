import base64

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa

private_key: rsa.RSAPrivateKey = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048
)

private_key_der: bytes = private_key.private_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
public_key_der: bytes = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.DER,
    format=serialization.PublicFormat.PKCS1,
)
private_key: str = private_key_der.hex()
public_key: str = base64.b64encode(public_key_der).decode()

public_key_hash = hashes.Hash(hashes.SHA256())
public_key_hash.update(public_key_der)
api_key: bytes = public_key_hash.finalize()
api_key_base64: str = base64.b64encode(api_key).decode()

print(
    f"""
    The private key is: {private_key}
    The public key is: {public_key}
    SHA256 hash of your public key in Base64 format is: {api_key_base64}
    """
)