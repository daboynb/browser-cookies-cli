"""Cookie extraction for Firefox (standard, snap, flatpak) on Linux, macOS, Windows."""

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path


def _find_default_profile(base_dir):
    """Find the default Firefox profile directory containing cookies.sqlite."""
    base = Path(base_dir)
    if not base.exists():
        return None

    # Try profiles.ini first
    profiles_ini = base / "profiles.ini"
    if profiles_ini.exists():
        import configparser
        config = configparser.ConfigParser()
        config.read(str(profiles_ini))
        for section in config.sections():
            if config.has_option(section, "Default") and config.get(section, "Default") == "1":
                if config.has_option(section, "Path"):
                    profile_path = base / config.get(section, "Path")
                    cookies = profile_path / "cookies.sqlite"
                    if cookies.exists():
                        return str(cookies)

    # Fallback: find profiles with .default suffix
    for entry in sorted(base.iterdir()):
        if entry.is_dir() and ".default" in entry.name:
            cookies = entry / "cookies.sqlite"
            if cookies.exists():
                return str(cookies)

    # Last resort: any directory with cookies.sqlite
    for entry in sorted(base.iterdir()):
        if entry.is_dir():
            cookies = entry / "cookies.sqlite"
            if cookies.exists():
                return str(cookies)

    return None


def _firefox_finders():
    """Return platform-specific Firefox profile finders."""
    home = Path.home()
    finders = []

    if sys.platform == "linux":
        finders.append(lambda: _find_default_profile(home / ".mozilla/firefox"))
        finders.append(lambda: _find_default_profile(home / "snap/firefox/common/.mozilla/firefox"))
        finders.append(lambda: _find_default_profile(home / ".var/app/org.mozilla.firefox/.mozilla/firefox"))

    elif sys.platform == "darwin":
        finders.append(lambda: _find_default_profile(home / "Library/Application Support/Firefox/Profiles"))
        # Also check the parent dir in case profiles.ini is one level up
        finders.append(lambda: _find_default_profile(home / "Library/Application Support/Firefox"))

    elif sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", ""))
        finders.append(lambda: _find_default_profile(appdata / "Mozilla/Firefox/Profiles"))
        finders.append(lambda: _find_default_profile(appdata / "Mozilla/Firefox"))

    return finders


FIREFOX_LOCATIONS = {
    "firefox": _firefox_finders(),
}


def read_firefox_cookies(db_path, browser_name, domain=None):
    """Read cookies from a Firefox SQLite database (unencrypted)."""
    tmp = tempfile.mktemp(suffix=".db")
    shutil.copy2(db_path, tmp)
    try:
        conn = sqlite3.connect(tmp)
        if domain:
            query = (
                "SELECT host, name, value, path, expiry, isSecure, isHttpOnly "
                "FROM moz_cookies WHERE host LIKE ?"
            )
            rows = conn.execute(query, (f"%{domain}%",))
        else:
            query = (
                "SELECT host, name, value, path, expiry, isSecure, isHttpOnly "
                "FROM moz_cookies"
            )
            rows = conn.execute(query)

        cookies = []
        for host, name, value, path, expires, secure, httponly in rows:
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


def write_firefox_cookies(cookies, db_path, browser_name):
    """Write cookies into a Firefox cookie database.

    Browser must be closed. Returns number of cookies written.
    """
    import time

    conn = sqlite3.connect(db_path)
    try:
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(moz_cookies)")}
        now_us = int(time.time() * 1_000_000)
        count = 0

        for cookie in cookies:
            expires = cookie.get("expires", 0)
            # Convert from Chromium microseconds-since-1601 if needed
            if expires > 1e13:
                expires = int(expires / 1_000_000 - 11644473600)

            row = {
                "originAttributes": "",
                "name": cookie["name"],
                "value": cookie["value"],
                "host": cookie["host"],
                "path": cookie.get("path", "/"),
                "expiry": int(expires),
                "lastAccessed": now_us,
                "creationTime": now_us + count,
                "isSecure": int(cookie.get("secure", False)),
                "isHttpOnly": int(cookie.get("httponly", False)),
                "inBrowserElement": 0,
                "sameSite": 0,
                "rawSameSite": 0,
                "schemeMap": 0,
            }

            filtered = {k: v for k, v in row.items() if k in existing_cols}
            col_names = ", ".join(filtered.keys())
            placeholders = ", ".join(["?"] * len(filtered))
            conn.execute(
                f"INSERT OR REPLACE INTO moz_cookies ({col_names}) VALUES ({placeholders})",
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
