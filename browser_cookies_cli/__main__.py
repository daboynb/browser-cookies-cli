"""CLI entry point: python -m browser_cookies_cli"""

import argparse
import json
import shutil
import subprocess
import sys

from browser_cookies_cli import detect_browsers, get_cookies, import_cookies
from browser_cookies_cli.formats import parse_cookies

SUPPORTED_BROWSERS = {"chrome", "brave", "chromium", "edge", "firefox"}


def _detect_version(browser_name):
    """Best-effort browser version detection."""
    candidates = {
        "chrome": ["google-chrome-stable", "google-chrome", "chrome"],
        "brave": ["brave-browser", "brave"],
        "chromium": ["chromium-browser", "chromium"],
        "edge": ["microsoft-edge", "microsoft-edge-stable"],
        "firefox": ["firefox"],
    }
    for binary in candidates.get(browser_name, []):
        if shutil.which(binary):
            try:
                result = subprocess.run(
                    [binary, "--version"], capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except (subprocess.TimeoutExpired, OSError):
                pass
    return None


def _choose_source(available):
    """Interactive browser selection for export. Returns browser name or None (all)."""
    names = list(available)

    print("Detected browsers:")
    for i, name in enumerate(names, 1):
        info = available[name]
        print(f"  [{i}] {name} ({info['type']}): {info['db']}")

    print(f"\nExport from:")
    print(f"  [a] All detected browsers")
    for i, name in enumerate(names, 1):
        print(f"  [{i}] {name} only")

    try:
        choice = input("\nChoice: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)

    if choice == "a":
        return None
    if choice.isdigit() and 1 <= int(choice) <= len(names):
        return names[int(choice) - 1]

    print("Invalid choice.", file=sys.stderr)
    sys.exit(1)


def _choose_targets(available):
    """Interactive browser selection. Returns list of browser names."""
    names = list(available)

    print("Detected browsers:")
    for i, name in enumerate(names, 1):
        info = available[name]
        print(f"  [{i}] {name} ({info['type']}): {info['db']}")

    missing = sorted(SUPPORTED_BROWSERS - set(names))
    if missing:
        print(f"\nNot installed: {', '.join(missing)}")

    print(f"\nImport into:")
    print(f"  [a] All detected browsers")
    for i, name in enumerate(names, 1):
        print(f"  [{i}] {name} only")

    try:
        choice = input("\nChoice: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.", file=sys.stderr)
        sys.exit(1)

    if choice == "a":
        return names
    if choice.isdigit() and 1 <= int(choice) <= len(names):
        return [names[int(choice) - 1]]

    print("Invalid choice.", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="browser-cookies",
        description="Export and import browser cookies",
    )
    sub = parser.add_subparsers(dest="command")

    export_cmd = sub.add_parser("export", help="Export cookies as JSON to stdout")
    export_cmd.add_argument("browser", nargs="?", help="Browser name (default: all detected)")

    import_cmd = sub.add_parser("import", help="Import cookies from a file")
    import_cmd.add_argument("file", help="Cookie file (JSON or Netscape)")
    import_cmd.add_argument("browser", nargs="?", help="Target browser (skip prompt)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "export":
        if args.browser:
            browser = args.browser
        elif sys.stdin.isatty():
            available = detect_browsers()
            if not available:
                print("No browsers detected.", file=sys.stderr)
                sys.exit(1)
            browser = _choose_source(available)
        else:
            browser = None  # all

        cookies, errors = get_cookies(browser=browser)

        for err in errors:
            print(f"[warn] {err}", file=sys.stderr)

        if not cookies:
            print("No cookies found.", file=sys.stderr)
            sys.exit(1)

        versions = {}
        for name in {c["browser"] for c in cookies}:
            v = _detect_version(name)
            if v:
                versions[name] = v

        output = {"cookies": cookies}
        if versions:
            output["versions"] = versions
        print(json.dumps(output, indent=2))

    elif args.command == "import":
        with open(args.file, "r") as f:
            text = f.read()

        stripped = text.strip()
        fmt = "json" if stripped.startswith(("[", "{")) else "netscape"
        cookies = parse_cookies(text, fmt)

        available = detect_browsers()
        if not available:
            print("No browsers detected.", file=sys.stderr)
            sys.exit(1)

        if args.browser:
            targets = [args.browser]
        elif sys.stdin.isatty():
            targets = _choose_targets(available)
        else:
            targets = list(available)

        total = 0
        for target in targets:
            count, errors = import_cookies(cookies, target)
            for err in errors:
                print(f"[warn] {err}", file=sys.stderr)
            if count:
                print(f"Imported {count} cookies into {target}.")
                total += count

        if not total:
            print("No cookies imported.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
