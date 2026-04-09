"""Create a Firefox profile with cookies.sqlite for testing (cross-platform)."""

import configparser
import os
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Platform-specific base directory
# ---------------------------------------------------------------------------

if sys.platform == "linux":
    base = Path.home() / ".mozilla/firefox"
elif sys.platform == "darwin":
    base = Path.home() / "Library/Application Support/Firefox"
elif sys.platform == "win32":
    base = Path(os.environ.get("APPDATA", "")) / "Mozilla/Firefox"
else:
    raise RuntimeError(f"Unsupported platform: {sys.platform}")

# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

profile_dir = base / "test.default"
profile_dir.mkdir(parents=True, exist_ok=True)

profiles_ini = base / "profiles.ini"
config = configparser.ConfigParser()
config["Profile0"] = {
    "Name": "default",
    "IsRelative": "1",
    "Path": "test.default",
    "Default": "1",
}
config["General"] = {"StartWithLastProfile": "1"}
with open(profiles_ini, "w") as f:
    config.write(f)

# ---------------------------------------------------------------------------
# cookies.sqlite
# ---------------------------------------------------------------------------

db_path = profile_dir / "cookies.sqlite"
conn = sqlite3.connect(str(db_path))
conn.execute("""
    CREATE TABLE IF NOT EXISTS moz_cookies (
        id INTEGER PRIMARY KEY,
        originAttributes TEXT NOT NULL DEFAULT '',
        name TEXT,
        value TEXT,
        host TEXT,
        path TEXT,
        expiry INTEGER,
        lastAccessed INTEGER,
        creationTime INTEGER,
        isSecure INTEGER,
        isHttpOnly INTEGER,
        inBrowserElement INTEGER DEFAULT 0,
        sameSite INTEGER DEFAULT 0,
        rawSameSite INTEGER DEFAULT 0,
        schemeMap INTEGER DEFAULT 0,
        CONSTRAINT moz_uniqueid UNIQUE (name, host, path, originAttributes)
    )
""")
conn.commit()
conn.close()

print(f"    Profile: {profile_dir}")
print(f"    Cookies DB: {db_path}")
