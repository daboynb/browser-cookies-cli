"""End-to-end: login on Chrome, export cookies, import into Firefox, verify session."""

import http.server
import socket
import sys
import threading
import unittest
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from browser_cookies_cli import import_cookies, get_cookies
from browser_cookies_cli.formats import format_cookies


# ---------------------------------------------------------------------------
# Minimal HTTP server with session auth
# ---------------------------------------------------------------------------

_sessions = set()


class _AuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/login":
            sid = uuid.uuid4().hex
            _sessions.add(sid)
            self.send_response(200)
            self.send_header("Set-Cookie", f"session={sid}; Path=/")
            self.end_headers()
            self.wfile.write(b"logged in")
        elif self.path == "/check":
            cookie_hdr = self.headers.get("Cookie", "")
            for part in cookie_hdr.split(";"):
                kv = part.strip()
                if kv.startswith("session=") and kv.split("=", 1)[1] in _sessions:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"authenticated")
                    return
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"not authenticated")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_):
        pass


def _free_port():
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

class TestE2E(unittest.TestCase):
    """Real browser session: Chrome login → export → import Firefox → verify."""

    @classmethod
    def setUpClass(cls):
        try:
            from selenium import webdriver as wd
            cls.webdriver = wd
        except ImportError:
            raise unittest.SkipTest("selenium not installed")

        cls.port = _free_port()
        cls.server = http.server.HTTPServer(("127.0.0.1", cls.port), _AuthHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_chrome_to_firefox_session(self):
        wd = self.webdriver

        # ---- Step 1: Login with real Chrome ----
        from selenium.webdriver.chrome.options import Options as ChromeOpts

        opts = ChromeOpts()
        opts.add_argument("--no-sandbox")
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-dev-shm-usage")

        chrome = wd.Chrome(options=opts)
        try:
            chrome.get(f"{self.url}/login")
            self.assertIn("logged in", chrome.page_source)

            # Get cookies via Selenium API (real session created by real Chrome)
            raw_cookies = chrome.get_cookies()
        finally:
            chrome.quit()

        session_raw = next((c for c in raw_cookies if c["name"] == "session"), None)
        self.assertIsNotNone(session_raw, f"No session cookie from Chrome. Got: {raw_cookies}")
        print(f"\n  [1/5] Chrome: logged in (session={session_raw['value'][:8]}...)")

        # ---- Step 2: Convert to our format ----
        cookies = []
        for c in raw_cookies:
            host = c.get("domain", "127.0.0.1")
            cookies.append({
                "host": host,
                "name": c["name"],
                "value": c["value"],
                "path": c.get("path", "/"),
                "expires": int(c.get("expiry", 0)),
                "secure": c.get("secure", False),
                "httponly": c.get("httpOnly", False),
            })
        print(f"  [2/5] Converted {len(cookies)} cookies")

        # ---- Step 3: Verify session with raw HTTP ----
        req = urllib.request.Request(f"{self.url}/check")
        req.add_header("Cookie", format_cookies(cookies, "header"))
        resp = urllib.request.urlopen(req)
        self.assertEqual(resp.read(), b"authenticated")
        print("  [3/5] HTTP verify: session valid")

        # ---- Step 4: Import into Firefox ----
        count, errors = import_cookies(cookies, "firefox")
        self.assertEqual(errors, [])
        self.assertGreater(count, 0)
        print(f"  [4/5] Imported {count} cookies into Firefox")

        # ---- Step 5: Read back from Firefox + verify with Firefox Selenium ----
        ff_cookies, errors = get_cookies(domain="127.0.0.1", browser="firefox")
        self.assertEqual(errors, [])
        ff_session = next((c for c in ff_cookies if c["name"] == "session"), None)
        self.assertIsNotNone(ff_session)
        self.assertEqual(ff_session["value"], session_raw["value"])

        from selenium.webdriver.firefox.options import Options as FFOpts

        ff_opts = FFOpts()
        ff_opts.add_argument("--headless")

        firefox = wd.Firefox(options=ff_opts)
        try:
            firefox.get(self.url)
            for c in ff_cookies:
                firefox.add_cookie({
                    "name": c["name"],
                    "value": c["value"],
                    "path": c.get("path", "/"),
                })
            firefox.get(f"{self.url}/check")
            self.assertIn("authenticated", firefox.page_source)
        finally:
            firefox.quit()

        print("  [5/5] Firefox: session verified — still authenticated!")


if __name__ == "__main__":
    unittest.main(verbosity=2)
