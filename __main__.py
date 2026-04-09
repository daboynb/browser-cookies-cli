"""CLI entry point: python -m browser_cookies_cli"""

import argparse
import sys

from browser_cookies_cli import detect_browsers, get_cookies, import_cookies
from browser_cookies_cli.formats import FORMATTERS, PARSERS, format_cookies, parse_cookies


def main():
    parser = argparse.ArgumentParser(
        prog="browser-cookies",
        description="Extract cookies from local browsers on Linux",
    )
    parser.add_argument("domain", nargs="?", help="Filter cookies by domain (substring match)")
    parser.add_argument("-b", "--browser", help="Browser name (e.g. brave, chrome, firefox)")
    parser.add_argument(
        "-f", "--format",
        choices=list(FORMATTERS),
        default=None,
        help="Output format for export / input format for import (default: header for export, auto-detect for import)",
    )
    parser.add_argument("--list", action="store_true", help="List detected browsers and exit")
    parser.add_argument(
        "--import", dest="import_file", metavar="FILE",
        help="Import cookies from a JSON or Netscape file into the target browser (requires -b)",
    )
    args = parser.parse_args()

    if args.list:
        browsers = detect_browsers()
        if not browsers:
            print("No supported browsers found.", file=sys.stderr)
            sys.exit(1)
        for name, info in browsers.items():
            print(f"{name} ({info['type']}): {info['db']}")
        return

    if args.import_file:
        if not args.browser:
            print("--import requires -b/--browser to specify the target browser.", file=sys.stderr)
            sys.exit(1)

        with open(args.import_file, "r") as f:
            text = f.read()

        fmt = args.format
        if not fmt:
            stripped = text.strip()
            if stripped.startswith("[") or stripped.startswith("{"):
                fmt = "json"
            else:
                fmt = "netscape"

        cookies = parse_cookies(text, fmt)
        count, errors = import_cookies(cookies, args.browser)

        for err in errors:
            print(f"[warn] {err}", file=sys.stderr)

        if count:
            print(f"Imported {count} cookies into {args.browser}.")
        else:
            print("No cookies imported.", file=sys.stderr)
            sys.exit(1)
        return

    cookies, errors = get_cookies(domain=args.domain, browser=args.browser)

    for err in errors:
        print(f"[warn] {err}", file=sys.stderr)

    if not cookies:
        print("No cookies found.", file=sys.stderr)
        sys.exit(1)

    print(format_cookies(cookies, args.format or "header"))


if __name__ == "__main__":
    main()
