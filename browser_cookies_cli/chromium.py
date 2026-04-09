"""Cookie extraction for Chromium-based browsers (Chrome, Brave, Chromium, Edge).

Supports Linux, macOS, and Windows.
"""

import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

from browser_cookies_cli.crypto import (
    _decrypt_value,
    _derive_key,
    _encrypt_value,
    _get_aes_key_windows,
    _get_password_linux,
    _get_password_macos,
)

_PLATFORM = sys.platform


def _browser_paths():
    """Return browser config per platform: {name: {cookie_paths, keyring_label, keychain_service}}."""
    home = Path.home()

    if _PLATFORM == "linux":
        return {
            "chrome": {
                "cookie_paths": [
                    home / ".config/google-chrome/Default/Network/Cookies",
                    home / ".config/google-chrome/Default/Cookies",
                    home / ".config/google-chrome/Profile 1/Network/Cookies",
                    home / ".config/google-chrome/Profile 1/Cookies",
                ],
                "keyring_label": "Chrome Safe Storage",
            },
            "brave": {
                "cookie_paths": [
                    home / ".config/BraveSoftware/Brave-Browser/Default/Network/Cookies",
                    home / ".config/BraveSoftware/Brave-Browser/Default/Cookies",
                    home / ".config/BraveSoftware/Brave-Browser/Profile 1/Network/Cookies",
                    home / ".config/BraveSoftware/Brave-Browser/Profile 1/Cookies",
                ],
                "keyring_label": "Brave Safe Storage",
            },
            "chromium": {
                "cookie_paths": [
                    home / ".config/chromium/Default/Network/Cookies",
                    home / ".config/chromium/Default/Cookies",
                    home / ".config/chromium/Profile 1/Network/Cookies",
                    home / ".config/chromium/Profile 1/Cookies",
                ],
                "keyring_label": "Chromium Safe Storage",
            },
            "edge": {
                "cookie_paths": [
                    home / ".config/microsoft-edge/Default/Network/Cookies",
                    home / ".config/microsoft-edge/Default/Cookies",
                    home / ".config/microsoft-edge/Profile 1/Network/Cookies",
                    home / ".config/microsoft-edge/Profile 1/Cookies",
                ],
                "keyring_label": "Microsoft Edge Safe Storage",
            },
        }

    elif _PLATFORM == "darwin":
        app_support = home / "Library/Application Support"
        return {
            "chrome": {
                "cookie_paths": [
                    app_support / "Google/Chrome/Default/Network/Cookies",
                    app_support / "Google/Chrome/Default/Cookies",
                    app_support / "Google/Chrome/Profile 1/Network/Cookies",
                    app_support / "Google/Chrome/Profile 1/Cookies",
                ],
                "keychain_service": "Chrome Safe Storage",
            },
            "brave": {
                "cookie_paths": [
                    app_support / "BraveSoftware/Brave-Browser/Default/Network/Cookies",
                    app_support / "BraveSoftware/Brave-Browser/Default/Cookies",
                    app_support / "BraveSoftware/Brave-Browser/Profile 1/Network/Cookies",
                    app_support / "BraveSoftware/Brave-Browser/Profile 1/Cookies",
                ],
                "keychain_service": "Brave Safe Storage",
            },
            "chromium": {
                "cookie_paths": [
                    app_support / "Chromium/Default/Network/Cookies",
                    app_support / "Chromium/Default/Cookies",
                    app_support / "Chromium/Profile 1/Network/Cookies",
                    app_support / "Chromium/Profile 1/Cookies",
                ],
                "keychain_service": "Chromium Safe Storage",
            },
            "edge": {
                "cookie_paths": [
                    app_support / "Microsoft Edge/Default/Network/Cookies",
                    app_support / "Microsoft Edge/Default/Cookies",
                    app_support / "Microsoft Edge/Profile 1/Network/Cookies",
                    app_support / "Microsoft Edge/Profile 1/Cookies",
                ],
                "keychain_service": "Microsoft Edge Safe Storage",
            },
        }

    elif _PLATFORM == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        return {
            "chrome": {
                "cookie_paths": [
                    local / "Google/Chrome/User Data/Default/Network/Cookies",
                    local / "Google/Chrome/User Data/Default/Cookies",
                    local / "Google/Chrome/User Data/Profile 1/Network/Cookies",
                ],
                "local_state": local / "Google/Chrome/User Data/Local State",
            },
            "brave": {
                "cookie_paths": [
                    local / "BraveSoftware/Brave-Browser/User Data/Default/Network/Cookies",
                    local / "BraveSoftware/Brave-Browser/User Data/Default/Cookies",
                    local / "BraveSoftware/Brave-Browser/User Data/Profile 1/Network/Cookies",
                ],
                "local_state": local / "BraveSoftware/Brave-Browser/User Data/Local State",
            },
            "chromium": {
                "cookie_paths": [
                    local / "Chromium/User Data/Default/Network/Cookies",
                    local / "Chromium/User Data/Default/Cookies",
                ],
                "local_state": local / "Chromium/User Data/Local State",
            },
            "edge": {
                "cookie_paths": [
                    local / "Microsoft/Edge/User Data/Default/Network/Cookies",
                    local / "Microsoft/Edge/User Data/Default/Cookies",
                ],
                "local_state": local / "Microsoft/Edge/User Data/Local State",
            },
        }

    return {}


CHROMIUM_BROWSERS = _browser_paths()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def read_chromium_cookies(db_path, browser_info, browser_name, domain=None):
    """Read and decrypt cookies from a Chromium-based browser."""
    # Get decryption key(s)
    aes_key = None
    win_key = None

    if _PLATFORM == "linux":
        password = _get_password_linux(browser_info["keyring_label"])
        aes_key = _derive_key(password, iterations=1)
    elif _PLATFORM == "darwin":
        password = _get_password_macos(browser_info["keychain_service"])
        aes_key = _derive_key(password, iterations=1003)
    elif _PLATFORM == "win32":
        local_state = browser_info.get("local_state")
        if local_state and Path(local_state).exists():
            win_key = _get_aes_key_windows(local_state)

    tmp = tempfile.mktemp(suffix=".db")
    for _attempt in range(3):
        try:
            shutil.copy2(db_path, tmp)
            break
        except PermissionError:
            if _attempt < 2:
                time.sleep(0.1)
            else:
                raise
    try:
        conn = sqlite3.connect(tmp)
        if domain:
            query = (
                "SELECT host_key, name, encrypted_value, value, path, "
                "expires_utc, is_secure, is_httponly FROM cookies WHERE host_key LIKE ?"
            )
            rows = conn.execute(query, (f"%{domain}%",))
        else:
            query = (
                "SELECT host_key, name, encrypted_value, value, path, "
                "expires_utc, is_secure, is_httponly FROM cookies"
            )
            rows = conn.execute(query)

        cookies = []
        for host, name, enc_val, val, path, expires, secure, httponly in rows:
            if val:
                value = val
            elif enc_val:
                value = _decrypt_value(enc_val, aes_key=aes_key, win_key=win_key)
            else:
                value = ""
            cookies.append({
                "host": host,
                "name": name,
                "value": value,
                "path": path,
                "expires": expires,
                "secure": bool(secure),
                "httponly": bool(httponly),
                "browser": browser_name,
            })
        conn.close()
        return cookies
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


_CHROMIUM_EPOCH_DELTA = 11644473600  # seconds between 1601-01-01 and 1970-01-01


def _to_chromium_ts(expires):
    """Convert an expires value to Chromium microseconds since 1601-01-01."""
    if expires > 1e13:
        return int(expires)
    return int((expires + _CHROMIUM_EPOCH_DELTA) * 1_000_000)


def _now_chromium():
    return int((time.time() + _CHROMIUM_EPOCH_DELTA) * 1_000_000)


def write_chromium_cookies(cookies, db_path, browser_info, browser_name):
    """Write cookies into a Chromium-based browser's cookie database.

    Browser must be closed. Returns number of cookies written.
    """
    aes_key = None
    win_key = None

    if _PLATFORM == "linux":
        password = _get_password_linux(browser_info["keyring_label"])
        aes_key = _derive_key(password, iterations=1)
    elif _PLATFORM == "darwin":
        password = _get_password_macos(browser_info["keychain_service"])
        aes_key = _derive_key(password, iterations=1003)
    elif _PLATFORM == "win32":
        local_state = browser_info.get("local_state")
        if local_state and Path(local_state).exists():
            win_key = _get_aes_key_windows(local_state)

    conn = sqlite3.connect(db_path)
    try:
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(cookies)")}
        now = _now_chromium()
        count = 0

        for cookie in cookies:
            host = cookie["host"]
            encrypted = _encrypt_value(cookie["value"], host, aes_key=aes_key, win_key=win_key)
            expires = _to_chromium_ts(cookie.get("expires", 0))

            row = {
                "creation_utc": now + count,
                "host_key": host,
                "top_frame_site_key": "",
                "name": cookie["name"],
                "value": "",
                "encrypted_value": encrypted,
                "path": cookie.get("path", "/"),
                "expires_utc": expires,
                "is_secure": int(cookie.get("secure", False)),
                "is_httponly": int(cookie.get("httponly", False)),
                "last_access_utc": now,
                "has_expires": 1 if expires > 0 else 0,
                "is_persistent": 1 if expires > 0 else 0,
                "priority": 1,
                "samesite": -1,
                "source_scheme": 2,
                "source_port": 443,
                "last_update_utc": now,
                "source_type": 1,
                "has_cross_site_ancestor": 1,
            }

            filtered = {k: v for k, v in row.items() if k in existing_cols}
            col_names = ", ".join(filtered.keys())
            placeholders = ", ".join(["?"] * len(filtered))
            conn.execute(
                f"INSERT OR REPLACE INTO cookies ({col_names}) VALUES ({placeholders})",
                list(filtered.values()),
            )
            count += 1

        conn.commit()
        return count
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            raise RuntimeError(
                f"Cannot write to {browser_name}: database is locked. Close the browser first."
            ) from e
        raise
    finally:
        conn.close()
