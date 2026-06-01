import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_KEY_SALT = b"xiaoai_class_schedule_v1"


def _derive_key() -> bytes:
    """Derive a Fernet key from a machine-specific secret."""
    secret = (os.environ.get("APP_SECRET") or _machine_id()).encode()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=_KEY_SALT, iterations=100_000)
    return base64.urlsafe_b64encode(kdf.derive(secret))


def _machine_id() -> str:
    try:
        with open("/etc/machine-id") as f:
            return f.read().strip()
    except Exception:
        pass
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
        val, _ = winreg.QueryValueEx(key, "MachineGuid")
        return val
    except Exception:
        return "fallback-secret-key-change-me"


_fernet = Fernet(_derive_key())


def encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()
