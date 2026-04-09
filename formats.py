"""Output formatters for extracted cookies."""

import json


def format_header(cookies):
    """Cookie: header value for HTTP requests."""
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies)


def format_json(cookies):
    """JSON array of cookie objects."""
    return json.dumps(cookies, indent=2)


def format_netscape(cookies):
    """Netscape/curl cookie jar format."""
    lines = ["# Netscape HTTP Cookie File", "# https://github.com/daboynb/browser-cookies-cli"]
    for c in cookies:
        domain = c["host"]
        flag = "TRUE" if domain.startswith(".") else "FALSE"
        secure = "TRUE" if c["secure"] else "FALSE"
        lines.append(
            f"{domain}\t{flag}\t{c['path']}\t{secure}\t{c['expires']}\t{c['name']}\t{c['value']}"
        )
    return "\n".join(lines)


FORMATTERS = {
    "header": format_header,
    "json": format_json,
    "netscape": format_netscape,
}


def format_cookies(cookies, fmt="header"):
    """Format cookies using the specified formatter."""
    if fmt not in FORMATTERS:
        raise ValueError(f"Unknown format '{fmt}'. Available: {', '.join(FORMATTERS)}")
    return FORMATTERS[fmt](cookies)


def parse_json(text):
    """Parse JSON array of cookie dicts."""
    cookies = json.loads(text)
    if not isinstance(cookies, list):
        raise ValueError("Expected a JSON array of cookies")
    return cookies


def parse_netscape(text):
    """Parse Netscape/curl cookie jar format."""
    cookies = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        cookies.append({
            "host": parts[0],
            "name": parts[5],
            "value": parts[6] if len(parts) > 6 else "",
            "path": parts[2],
            "expires": int(parts[4]),
            "secure": parts[3] == "TRUE",
            "httponly": False,
        })
    return cookies


PARSERS = {
    "json": parse_json,
    "netscape": parse_netscape,
}


def parse_cookies(text, fmt):
    """Parse cookies from text in the specified format."""
    if fmt not in PARSERS:
        raise ValueError(f"Unknown format '{fmt}'. Parseable: {', '.join(PARSERS)}")
    return PARSERS[fmt](text)
