"""Extract cookies from local browsers (Linux, macOS, Windows)."""

from browser_cookies_cli.chromium import CHROMIUM_BROWSERS, read_chromium_cookies, write_chromium_cookies
from browser_cookies_cli.firefox import FIREFOX_LOCATIONS, read_firefox_cookies, write_firefox_cookies
from browser_cookies_cli.formats import format_cookies

__version__ = "0.1.0"


def detect_browsers():
    """Return dict of {browser_name: info} for all browsers found on this system."""
    found = {}
    for name, info in CHROMIUM_BROWSERS.items():
        for db_path in info["cookie_paths"]:
            if db_path.exists():
                found[name] = {"type": "chromium", "db": str(db_path), "info": info}
                break
    for name, finders in FIREFOX_LOCATIONS.items():
        for resolver in finders:
            result = resolver()
            if result:
                found[name] = {"type": "firefox", "db": result}
                break
    return found


def get_cookies(domain=None, browser=None):
    """Extract cookies, optionally filtered by domain and browser name.

    Returns (cookies, errors) where cookies is a list of dicts with keys:
        host, name, value, path, expires, secure, httponly, browser
    """
    available = detect_browsers()

    if browser:
        if browser not in available:
            raise ValueError(f"Browser '{browser}' not found. Available: {', '.join(available) or 'none'}")
        available = {browser: available[browser]}

    cookies = []
    errors = []
    for name, entry in available.items():
        try:
            if entry["type"] == "chromium":
                cookies.extend(read_chromium_cookies(entry["db"], entry["info"], name, domain))
            elif entry["type"] == "firefox":
                cookies.extend(read_firefox_cookies(entry["db"], name, domain))
        except Exception as e:
            errors.append(f"{name}: {e}")

    return cookies, errors


def import_cookies(cookies, browser):
    """Import cookies into the specified browser.

    Browser must be closed. Returns (count, errors).
    """
    available = detect_browsers()
    if browser not in available:
        raise ValueError(f"Browser '{browser}' not found. Available: {', '.join(available) or 'none'}")

    entry = available[browser]
    errors = []
    count = 0

    try:
        if entry["type"] == "chromium":
            count = write_chromium_cookies(cookies, entry["db"], entry["info"], browser)
        elif entry["type"] == "firefox":
            count = write_firefox_cookies(cookies, entry["db"], browser)
    except Exception as e:
        errors.append(f"{browser}: {e}")

    return count, errors
