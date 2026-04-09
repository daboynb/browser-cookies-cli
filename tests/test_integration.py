"""Integration tests: cookie import/export with real Chrome and Firefox on Linux."""

import json
import sqlite3
import sys
import unittest
from pathlib import Path

# PYTHONPATH is set by Docker; this fallback handles local runs
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from browser_cookies_cli import detect_browsers, get_cookies, import_cookies
from browser_cookies_cli.formats import format_cookies, parse_cookies


class TestDetectBrowsers(unittest.TestCase):

    def test_chrome_detected(self):
        browsers = detect_browsers()
        self.assertIn("chrome", browsers, f"Chrome not found. Detected: {list(browsers)}")
        self.assertEqual(browsers["chrome"]["type"], "chromium")
        print(f"  Chrome DB: {browsers['chrome']['db']}")

    def test_firefox_detected(self):
        browsers = detect_browsers()
        self.assertIn("firefox", browsers, f"Firefox not found. Detected: {list(browsers)}")
        self.assertEqual(browsers["firefox"]["type"], "firefox")
        print(f"  Firefox DB: {browsers['firefox']['db']}")


class TestChromeSchema(unittest.TestCase):

    def test_expected_columns_exist(self):
        browsers = detect_browsers()
        db_path = browsers["chrome"]["db"]
        conn = sqlite3.connect(db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(cookies)")}
        conn.close()

        required = {
            "host_key", "name", "value", "encrypted_value",
            "path", "expires_utc", "is_secure", "is_httponly",
        }
        missing = required - cols
        self.assertFalse(missing, f"Missing columns: {missing}")
        print(f"  Schema has {len(cols)} columns: {sorted(cols)}")


class TestChromeImportExport(unittest.TestCase):

    COOKIES = [
        {
            "host": ".example.com",
            "name": "session_id",
            "value": "abc123",
            "path": "/",
            "expires": 1900000000,
            "secure": True,
            "httponly": True,
        },
        {
            "host": ".test.org",
            "name": "pref",
            "value": "dark_mode=1",
            "path": "/settings",
            "expires": 1900000000,
            "secure": False,
            "httponly": False,
        },
    ]

    def test_import_and_readback(self):
        count, errors = import_cookies(self.COOKIES, "chrome")
        self.assertEqual(errors, [], f"Import errors: {errors}")
        self.assertEqual(count, 2)

        cookies, errors = get_cookies(domain="example.com", browser="chrome")
        self.assertEqual(errors, [])
        self.assertTrue(len(cookies) >= 1, "No cookies after import")

        found = next((c for c in cookies if c["name"] == "session_id"), None)
        self.assertIsNotNone(found, f"session_id not in {[c['name'] for c in cookies]}")
        self.assertEqual(found["value"], "abc123")
        self.assertEqual(found["host"], ".example.com")

    def test_json_roundtrip(self):
        import_cookies(self.COOKIES, "chrome")
        cookies, _ = get_cookies(browser="chrome")
        json_text = format_cookies(cookies, "json")
        parsed = parse_cookies(json_text, "json")
        names = {c["name"] for c in parsed}
        self.assertIn("session_id", names)
        self.assertIn("pref", names)

    def test_netscape_roundtrip(self):
        import_cookies(self.COOKIES, "chrome")
        cookies, _ = get_cookies(browser="chrome")
        ns_text = format_cookies(cookies, "netscape")
        parsed = parse_cookies(ns_text, "netscape")
        names = {c["name"] for c in parsed}
        self.assertIn("session_id", names)


class TestFirefoxImportExport(unittest.TestCase):

    COOKIES = [
        {
            "host": ".fftest.example.com",
            "name": "ff_session",
            "value": "xyz789",
            "path": "/",
            "expires": 1900000000,
            "secure": True,
            "httponly": False,
        },
    ]

    def test_import_and_readback(self):
        count, errors = import_cookies(self.COOKIES, "firefox")
        self.assertEqual(errors, [], f"Import errors: {errors}")
        self.assertEqual(count, 1)

        cookies, errors = get_cookies(domain="fftest.example.com", browser="firefox")
        self.assertEqual(errors, [])
        found = next((c for c in cookies if c["name"] == "ff_session"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["value"], "xyz789")


class TestCrossBrowser(unittest.TestCase):

    def test_chrome_to_firefox(self):
        src = [{
            "host": ".cross.example.com",
            "name": "cross_test",
            "value": "from_chrome",
            "path": "/",
            "expires": 1900000000,
            "secure": True,
            "httponly": False,
        }]
        import_cookies(src, "chrome")

        cookies, _ = get_cookies(domain="cross.example.com", browser="chrome")
        self.assertTrue(len(cookies) >= 1)

        count, errors = import_cookies(cookies, "firefox")
        self.assertEqual(errors, [])

        ff_cookies, _ = get_cookies(domain="cross.example.com", browser="firefox")
        found = next((c for c in ff_cookies if c["name"] == "cross_test"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["value"], "from_chrome")

    def test_firefox_to_chrome(self):
        src = [{
            "host": ".reverse.example.com",
            "name": "reverse_test",
            "value": "from_firefox",
            "path": "/",
            "expires": 1900000000,
            "secure": False,
            "httponly": True,
        }]
        import_cookies(src, "firefox")

        cookies, _ = get_cookies(domain="reverse.example.com", browser="firefox")
        self.assertTrue(len(cookies) >= 1)

        count, errors = import_cookies(cookies, "chrome")
        self.assertEqual(errors, [])

        cr_cookies, _ = get_cookies(domain="reverse.example.com", browser="chrome")
        found = next((c for c in cr_cookies if c["name"] == "reverse_test"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["value"], "from_firefox")


if __name__ == "__main__":
    unittest.main(verbosity=2)
