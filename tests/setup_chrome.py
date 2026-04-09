"""Create a Chrome profile with Cookies DB (schema v24) and platform-specific encryption key."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Platform-specific: profile path + encryption key setup
# ---------------------------------------------------------------------------

if sys.platform == "linux":
    network_dir = Path.home() / ".config/google-chrome/Default/Network"

    import secretstorage

    bus = secretstorage.dbus_init()
    collection = secretstorage.get_default_collection(bus)
    if collection.is_locked():
        collection.unlock()
    collection.create_item(
        "Chrome Safe Storage",
        {"application": "chrome"},
        b"test_chrome_password",
        replace=True,
    )
    print("    Keyring: Chrome Safe Storage stored")

elif sys.platform == "darwin":
    network_dir = (
        Path.home() / "Library/Application Support/Google/Chrome/Default/Network"
    )

    subprocess.run(
        ["security", "delete-generic-password", "-s", "Chrome Safe Storage"],
        capture_output=True,
    )
    subprocess.run(
        [
            "security", "add-generic-password",
            "-a", "Chrome",
            "-s", "Chrome Safe Storage",
            "-w", "test_chrome_password",
        ],
        check=True,
    )
    print("    Keychain: Chrome Safe Storage stored")

elif sys.platform == "win32":
    import base64

    local = Path(os.environ.get("LOCALAPPDATA", ""))
    user_data = local / "Google/Chrome/User Data"
    network_dir = user_data / "Default/Network"

    aes_key = os.urandom(32)

    import win32crypt  # type: ignore[import-not-found]

    encrypted = win32crypt.CryptProtectData(aes_key, None, None, None, None, 0)
    encrypted_key_b64 = base64.b64encode(b"DPAPI" + encrypted).decode()

    local_state_path = user_data / "Local State"
    user_data.mkdir(parents=True, exist_ok=True)
    with open(local_state_path, "w") as f:
        json.dump({"os_crypt": {"encrypted_key": encrypted_key_b64}}, f)
    print(f"    Local State: {local_state_path}")

else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")

# ---------------------------------------------------------------------------
# Cookies DB with schema v24
# ---------------------------------------------------------------------------

network_dir.mkdir(parents=True, exist_ok=True)
db_path = network_dir / "Cookies"

conn = sqlite3.connect(str(db_path))
conn.executescript("""
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT NOT NULL UNIQUE PRIMARY KEY,
        value TEXT
    );
    INSERT OR REPLACE INTO meta (key, value) VALUES ('version', '24');

    CREATE TABLE IF NOT EXISTS cookies (
        creation_utc INTEGER NOT NULL,
        host_key TEXT NOT NULL,
        top_frame_site_key TEXT NOT NULL,
        name TEXT NOT NULL,
        value TEXT NOT NULL,
        encrypted_value BLOB NOT NULL,
        path TEXT NOT NULL,
        expires_utc INTEGER NOT NULL,
        is_secure INTEGER NOT NULL,
        is_httponly INTEGER NOT NULL,
        last_access_utc INTEGER NOT NULL,
        has_expires INTEGER NOT NULL,
        is_persistent INTEGER NOT NULL,
        priority INTEGER NOT NULL,
        samesite INTEGER NOT NULL,
        source_scheme INTEGER NOT NULL,
        source_port INTEGER NOT NULL,
        last_update_utc INTEGER NOT NULL,
        source_type INTEGER NOT NULL,
        has_cross_site_ancestor INTEGER NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS cookies_unique_index ON cookies (
        host_key, top_frame_site_key, has_cross_site_ancestor,
        name, path, source_scheme, source_port
    );
""")
conn.close()

print(f"    Cookies DB: {db_path}")
