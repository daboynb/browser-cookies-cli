"""Chromium cookie decryption: password retrieval, key derivation, and decryption."""

import hashlib
import json
import os
import subprocess
import sys

_PLATFORM = sys.platform


# ---------------------------------------------------------------------------
# Linux: GNOME Keyring / Secret Service
# ---------------------------------------------------------------------------

def _get_password_linux(keyring_label):
    import secretstorage

    bus = secretstorage.dbus_init()
    col = secretstorage.get_default_collection(bus)
    if col.is_locked():
        col.unlock()

    for item in col.get_all_items():
        if item.get_label() == keyring_label:
            return item.get_secret()

    raise RuntimeError(f"'{keyring_label}' not found in keyring")


# ---------------------------------------------------------------------------
# macOS: Keychain
# ---------------------------------------------------------------------------

def _get_password_macos(service_name):
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service_name, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Keychain lookup failed for '{service_name}': {result.stderr.strip()}")
    return result.stdout.strip().encode("utf-8")


# ---------------------------------------------------------------------------
# Windows: DPAPI + AES-GCM (v80/v20 key from Local State)
# ---------------------------------------------------------------------------

def _get_aes_key_windows(local_state_path):
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.load(f)

    import base64
    encrypted_key_b64 = local_state["os_crypt"]["encrypted_key"]
    encrypted_key = base64.b64decode(encrypted_key_b64)

    # Strip "DPAPI" prefix (5 bytes)
    encrypted_key = encrypted_key[5:]

    import win32crypt  # type: ignore[import-not-found]
    _, decrypted_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)
    return decrypted_key


def _strip_sha256_prefix(decrypted):
    """Strip optional SHA256(host_key) prefix (32 bytes) from decrypted value."""
    if len(decrypted) > 32:
        tail = decrypted[32:]
        try:
            tail.decode("utf-8")
            return tail.decode("utf-8")
        except UnicodeDecodeError:
            pass
    return decrypted.decode("utf-8", errors="replace")


def _decrypt_windows_v80(encrypted_value, aes_key):
    """Decrypt v80 (AES-256-GCM) cookie on Windows."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = encrypted_value[3:15]  # 12 bytes after "v80" or "v20"
    ciphertext_tag = encrypted_value[15:]
    decrypted = AESGCM(aes_key).decrypt(nonce, ciphertext_tag, None)
    return _strip_sha256_prefix(decrypted)


def _decrypt_windows_dpapi(encrypted_value):
    """Decrypt DPAPI-only cookie on Windows (older Chrome)."""
    import win32crypt  # type: ignore[import-not-found]
    _, decrypted = win32crypt.CryptUnprotectData(encrypted_value, None, None, None, 0)
    return _strip_sha256_prefix(decrypted)


# ---------------------------------------------------------------------------
# Key derivation (Linux / macOS)
# ---------------------------------------------------------------------------

def _derive_key(password, iterations=1):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(algorithm=hashes.SHA1(), length=16, salt=b"saltysalt", iterations=iterations)
    return kdf.derive(password)


# ---------------------------------------------------------------------------
# Decryption dispatcher
# ---------------------------------------------------------------------------

def _decrypt_value(encrypted_value, aes_key=None, win_key=None):
    """Decrypt a Chromium encrypted cookie value (cross-platform)."""
    if not encrypted_value:
        return ""

    prefix = encrypted_value[:3]

    # Windows v80/v20 (AES-256-GCM)
    if _PLATFORM == "win32" and prefix in (b"v80", b"v20", b"v10"):
        if prefix in (b"v80", b"v20") and win_key:
            return _decrypt_windows_v80(encrypted_value, win_key)
        elif prefix == b"v10":
            return _decrypt_windows_dpapi(encrypted_value)
        return ""

    # Linux / macOS: v10/v11 (AES-128-CBC)
    if prefix not in (b"v10", b"v11"):
        return encrypted_value.decode("utf-8", errors="replace")

    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    enc_data = encrypted_value[3:]
    if not enc_data or len(enc_data) % 16 != 0:
        return ""

    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(b" " * 16))
    dec = cipher.decryptor()
    decrypted = dec.update(enc_data) + dec.finalize()

    # Remove PKCS7 padding
    pad_len = decrypted[-1]
    if 0 < pad_len <= 16:
        decrypted = decrypted[:-pad_len]

    return _strip_sha256_prefix(decrypted)


def _encrypt_linux_macos(payload, aes_key):
    """Encrypt with AES-128-CBC (v10 prefix) for Linux/macOS."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    pad_len = 16 - (len(payload) % 16)
    padded = payload + bytes([pad_len] * pad_len)
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(b" " * 16))
    enc = cipher.encryptor()
    return b"v10" + enc.update(padded) + enc.finalize()


def _encrypt_windows_v80(payload, win_key):
    """Encrypt with AES-256-GCM (v80 prefix) for Windows."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    return b"v80" + nonce + AESGCM(win_key).encrypt(nonce, payload, None)


def _encrypt_value(plaintext, host_key, aes_key=None, win_key=None):
    """Encrypt a cookie value for Chromium (cross-platform).

    Prepends SHA256(host_key) to the plaintext before encryption (schema v24+).
    """
    if not plaintext:
        return b""

    payload = hashlib.sha256(host_key.encode()).digest() + plaintext.encode("utf-8")

    if _PLATFORM == "win32" and win_key:
        return _encrypt_windows_v80(payload, win_key)
    if aes_key:
        return _encrypt_linux_macos(payload, aes_key)
    return b""
