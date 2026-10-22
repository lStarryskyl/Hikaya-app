"""Password hashing and session tokens, using only the standard library.

Passwords use scrypt with a random salt. The parameters are stored inside each hash
string, so they can be raised later without breaking existing accounts.
Session tokens are random; only their SHA-256 is stored, so a leaked database
cannot be used to sign in.
"""

import base64
import hashlib
import hmac
import secrets

_N = 2**15
_R = 8
_P = 1
_KEY_LEN = 32
_MAX_MEMORY = 64 * 1024 * 1024
# Refuse hashes asking for absurd work, so a corrupted row cannot hang a request.
_MAX_N = 2**17


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(
        password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAX_MEMORY, dklen=_KEY_LEN
    )
    return "$".join(
        ["scrypt", str(_N), str(_R), str(_P), _b64(salt), _b64(key)],
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, expected = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        if n < 2 or n > _MAX_N or n & (n - 1) or r < 1 or r > 32 or p < 1 or p > 8:
            return False
        salt_bytes, expected_bytes = _unb64(salt), _unb64(expected)
        key = hashlib.scrypt(
            password.encode(),
            salt=salt_bytes,
            n=n,
            r=r,
            p=p,
            maxmem=_MAX_MEMORY,
            dklen=len(expected_bytes),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(key, expected_bytes)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _unb64(text: str) -> bytes:
    return base64.b64decode(text, validate=True)
