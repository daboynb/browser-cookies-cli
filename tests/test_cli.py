"""Tests for CLI interactive flows, subcommands, and format auto-detection."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from browser_cookies_cli import get_cookies, import_cookies
from browser_cookies_cli.__main__ import _choose_source, _choose_targets
from browser_cookies_cli.formats import parse_cookies

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


def _run_cli(*args):
    """Run the CLI as a subprocess and return the CompletedProcess."""
    return subprocess.run(
        [sys.executable, "-m", "browser_cookies_cli", *args],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": _PROJECT_ROOT},
    )


# ---------------------------------------------------------------------------
# _choose_source (export interactive)
# ---------------------------------------------------------------------------

class TestChooseSource(unittest.TestCase):
    AVAILABLE = {
        "chrome": {"type": "chromium", "db": "/tmp/chrome/Cookies"},
        "firefox": {"type": "firefox", "db": "/tmp/firefox/cookies.sqlite"},
    }

    @patch("builtins.input", return_value="a")
    def test_all(self, _):
        result = _choose_source(self.AVAILABLE)
        self.assertIsNone(result)

    @patch("builtins.input", return_value="1")
    def test_first_browser(self, _):
        result = _choose_source(self.AVAILABLE)
        names = list(self.AVAILABLE)
        self.assertEqual(result, names[0])

    @patch("builtins.input", return_value="2")
    def test_second_browser(self, _):
        result = _choose_source(self.AVAILABLE)
        names = list(self.AVAILABLE)
        self.assertEqual(result, names[1])

    @patch("builtins.input", return_value="invalid")
    def test_invalid_exits(self, _):
        with self.assertRaises(SystemExit):
            _choose_source(self.AVAILABLE)

    @patch("builtins.input", return_value="0")
    def test_zero_exits(self, _):
        with self.assertRaises(SystemExit):
            _choose_source(self.AVAILABLE)

    @patch("builtins.input", return_value="99")
    def test_out_of_range_exits(self, _):
        with self.assertRaises(SystemExit):
            _choose_source(self.AVAILABLE)

    @patch("builtins.input", side_effect=EOFError)
    def test_eof_exits(self, _):
        with self.assertRaises(SystemExit):
            _choose_source(self.AVAILABLE)

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_ctrl_c_exits(self, _):
        with self.assertRaises(SystemExit):
            _choose_source(self.AVAILABLE)

    @patch("builtins.input", return_value="a")
    def test_prints_browser_list(self, _):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _choose_source(self.AVAILABLE)
        output = buf.getvalue()
        self.assertIn("chrome", output)
        self.assertIn("firefox", output)
        self.assertIn("[1]", output)
        self.assertIn("[2]", output)


# ---------------------------------------------------------------------------
# _choose_targets (import interactive)
# ---------------------------------------------------------------------------

class TestChooseTargets(unittest.TestCase):
    AVAILABLE = {
        "chrome": {"type": "chromium", "db": "/tmp/chrome/Cookies"},
        "firefox": {"type": "firefox", "db": "/tmp/firefox/cookies.sqlite"},
    }

    @patch("builtins.input", return_value="a")
    def test_all(self, _):
        result = _choose_targets(self.AVAILABLE)
        self.assertEqual(result, list(self.AVAILABLE))

    @patch("builtins.input", return_value="1")
    def test_specific(self, _):
        result = _choose_targets(self.AVAILABLE)
        self.assertEqual(result, [list(self.AVAILABLE)[0]])

    @patch("builtins.input", return_value="invalid")
    def test_invalid_exits(self, _):
        with self.assertRaises(SystemExit):
            _choose_targets(self.AVAILABLE)

    @patch("builtins.input", side_effect=EOFError)
    def test_eof_exits(self, _):
        with self.assertRaises(SystemExit):
            _choose_targets(self.AVAILABLE)

    @patch("builtins.input", return_value="a")
    def test_shows_not_installed(self, _):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _choose_targets(self.AVAILABLE)
        output = buf.getvalue()
        self.assertIn("Not installed:", output)
        self.assertIn("brave", output)

    @patch("builtins.input", return_value="a")
    def test_shows_import_prompt(self, _):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _choose_targets(self.AVAILABLE)
        output = buf.getvalue()
        self.assertIn("Import into:", output)
        self.assertIn("[a]", output)


# ---------------------------------------------------------------------------
# CLI subcommands via subprocess
# ---------------------------------------------------------------------------

class TestCLINoCommand(unittest.TestCase):

    def test_no_command_shows_help(self):
        r = _run_cli()
        self.assertNotEqual(r.returncode, 0)

    def test_help_flag(self):
        r = _run_cli("--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("export", r.stdout)
        self.assertIn("import", r.stdout)

    def test_export_help(self):
        r = _run_cli("export", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("browser", r.stdout.lower())

    def test_import_help(self):
        r = _run_cli("import", "--help")
        self.assertEqual(r.returncode, 0)
        self.assertIn("file", r.stdout.lower())


class TestCLIExport(unittest.TestCase):

    def test_export_chrome_json(self):
        r = _run_cli("export", "chrome")
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        data = json.loads(r.stdout)
        self.assertIn("cookies", data)
        self.assertIsInstance(data["cookies"], list)

    def test_export_firefox_json(self):
        r = _run_cli("export", "firefox")
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        data = json.loads(r.stdout)
        self.assertIn("cookies", data)

    def test_export_nonexistent_browser_fails(self):
        r = _run_cli("export", "nonexistent_browser")
        self.assertNotEqual(r.returncode, 0)

    def test_export_output_is_valid_json(self):
        r = _run_cli("export", "chrome")
        if r.returncode != 0:
            self.skipTest("No cookies in chrome")
        data = json.loads(r.stdout)
        for cookie in data["cookies"]:
            self.assertIn("host", cookie)
            self.assertIn("name", cookie)
            self.assertIn("value", cookie)
            self.assertIn("browser", cookie)


class TestCLIImport(unittest.TestCase):

    def _write_cookie_file(self, cookies, fmt="json"):
        f = tempfile.NamedTemporaryFile(mode="w", suffix=f".{fmt}", delete=False)
        if fmt == "json":
            json.dump({"cookies": cookies}, f)
        else:
            f.write("# Netscape HTTP Cookie File\n")
            for c in cookies:
                domain = c["host"]
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                secure = "TRUE" if c.get("secure") else "FALSE"
                f.write(f"{domain}\t{flag}\t{c['path']}\t{secure}\t{c['expires']}\t{c['name']}\t{c['value']}\n")
        f.close()
        return f.name

    def setUp(self):
        self._files = []

    def tearDown(self):
        for f in self._files:
            try:
                os.unlink(f)
            except OSError:
                pass

    def _tmp(self, cookies, fmt="json"):
        path = self._write_cookie_file(cookies, fmt)
        self._files.append(path)
        return path

    def test_import_json_into_firefox(self):
        path = self._tmp([{
            "host": ".cli-json.com", "name": "jc", "value": "json_val",
            "path": "/", "expires": 1900000000, "secure": False, "httponly": False,
        }])
        r = _run_cli("import", path, "firefox")
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")
        self.assertIn("Imported", r.stdout)

        cookies, _ = get_cookies(domain="cli-json.com", browser="firefox")
        found = next((c for c in cookies if c["name"] == "jc"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["value"], "json_val")

    def test_import_netscape_into_firefox(self):
        path = self._tmp([{
            "host": ".cli-ns.com", "name": "nc", "value": "ns_val",
            "path": "/", "expires": 1900000000, "secure": False,
        }], fmt="netscape")
        r = _run_cli("import", path, "firefox")
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")

        cookies, _ = get_cookies(domain="cli-ns.com", browser="firefox")
        found = next((c for c in cookies if c["name"] == "nc"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["value"], "ns_val")

    def test_import_json_into_chrome(self):
        path = self._tmp([{
            "host": ".cli-chrome.com", "name": "cc", "value": "chrome_val",
            "path": "/", "expires": 1900000000, "secure": False, "httponly": False,
        }])
        r = _run_cli("import", path, "chrome")
        self.assertEqual(r.returncode, 0, f"stderr: {r.stderr}")

        cookies, _ = get_cookies(domain="cli-chrome.com", browser="chrome")
        found = next((c for c in cookies if c["name"] == "cc"), None)
        self.assertIsNotNone(found)
        self.assertEqual(found["value"], "chrome_val")

    def test_import_nonexistent_file_fails(self):
        r = _run_cli("import", "/nonexistent/cookies.json", "firefox")
        self.assertNotEqual(r.returncode, 0)

    def test_import_into_nonexistent_browser_fails(self):
        path = self._tmp([{
            "host": ".x.com", "name": "x", "value": "x",
            "path": "/", "expires": 0, "secure": False, "httponly": False,
        }])
        r = _run_cli("import", path, "nonexistent_browser")
        self.assertNotEqual(r.returncode, 0)


class TestCLIRoundtrip(unittest.TestCase):
    """Full CLI roundtrip: import → export → import into other browser."""

    def test_chrome_export_firefox_import(self):
        import_cookies([{
            "host": ".cli-rt.com", "name": "rt", "value": "roundtrip_123",
            "path": "/", "expires": 1900000000, "secure": False, "httponly": False,
        }], "chrome")

        export_r = _run_cli("export", "chrome")
        self.assertEqual(export_r.returncode, 0)

        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(export_r.stdout)
        tmp.close()

        try:
            import_r = _run_cli("import", tmp.name, "firefox")
            self.assertEqual(import_r.returncode, 0, f"stderr: {import_r.stderr}")

            cookies, _ = get_cookies(domain="cli-rt.com", browser="firefox")
            found = next((c for c in cookies if c["name"] == "rt"), None)
            self.assertIsNotNone(found)
            self.assertEqual(found["value"], "roundtrip_123")
        finally:
            os.unlink(tmp.name)


# ---------------------------------------------------------------------------
# Format auto-detection
# ---------------------------------------------------------------------------

class TestFormatParsing(unittest.TestCase):

    def test_json_array(self):
        text = '[{"host": ".x.com", "name": "a", "value": "b", "path": "/", "expires": 0, "secure": false, "httponly": false}]'
        cookies = parse_cookies(text, "json")
        self.assertEqual(len(cookies), 1)
        self.assertEqual(cookies[0]["name"], "a")

    def test_json_object_with_cookies_key(self):
        text = '{"browser": "chrome", "cookies": [{"host": ".x.com", "name": "a", "value": "b"}]}'
        cookies = parse_cookies(text, "json")
        self.assertEqual(len(cookies), 1)

    def test_json_invalid_structure(self):
        with self.assertRaises(ValueError):
            parse_cookies('{"not_cookies": []}', "json")

    def test_json_invalid_syntax(self):
        with self.assertRaises(json.JSONDecodeError):
            parse_cookies("not json at all", "json")

    def test_netscape_basic(self):
        text = ".example.com\tTRUE\t/\tFALSE\t0\tname\tvalue"
        cookies = parse_cookies(text, "netscape")
        self.assertEqual(len(cookies), 1)
        self.assertEqual(cookies[0]["host"], ".example.com")
        self.assertEqual(cookies[0]["name"], "name")
        self.assertEqual(cookies[0]["value"], "value")
        self.assertTrue(cookies[0]["secure"] is False)

    def test_netscape_skips_comments(self):
        text = "# comment\n# another\n.x.com\tTRUE\t/\tTRUE\t0\ta\tb"
        cookies = parse_cookies(text, "netscape")
        self.assertEqual(len(cookies), 1)

    def test_netscape_skips_short_lines(self):
        text = "too\tfew\tfields\n.x.com\tTRUE\t/\tFALSE\t0\ta\tb"
        cookies = parse_cookies(text, "netscape")
        self.assertEqual(len(cookies), 1)

    def test_netscape_empty(self):
        text = "# Netscape HTTP Cookie File\n# just comments\n"
        cookies = parse_cookies(text, "netscape")
        self.assertEqual(len(cookies), 0)

    def test_unknown_format_raises(self):
        with self.assertRaises(ValueError):
            parse_cookies("anything", "xml")


if __name__ == "__main__":
    unittest.main(verbosity=2)
