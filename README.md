# browser-cookies-cli

> **⚠️ DEVELOPMENT STATUS:** This project is currently under active development and is not yet considered stable.

Cross-platform CLI that extracts cookies from Chrome, Brave, Chromium, Edge, and Firefox — through the OS-level key stores each browser hides behind (DPAPI on Windows, GNOME Keyring via Secret Service on Linux, Keychain on macOS).

> **Use on accounts you own. Cookie extraction is the last step before session hijack — treat the extracted files accordingly.**

## Why this is non-trivial

"Copy the Cookies file" stopped working in 2019. Chromium-based browsers store cookies in SQLite with the **cookie value itself encrypted** under a per-user key. The key does not live in the browser's files — it lives in the platform secret store. A tool that actually extracts usable cookies has to speak all three stores.

## Supported browsers and platforms

| Browser   | Linux | macOS | Windows |
|-----------|:---:|:---:|:---:|
| Chrome    | ✓ | ✓ | ✓ |
| Brave     | ✓ | ✓ | ✓ |
| Chromium  | ✓ | ✓ | ✓ |
| Edge      | ✓ | ✓ | ✓ |
| Firefox   | ✓ | ✓ | ✓ |

Firefox has no encryption on the cookie file — straight SQLite read. Chromium-based browsers need per-platform key retrieval:

- **Linux** — `secretstorage` (Secret Service D-Bus). Label: `<Browser> Safe Storage`. Unlocks the login keyring if locked.
- **macOS** — `security find-generic-password -s "<Browser> Safe Storage" -w`.
- **Windows** — `os_crypt.encrypted_key` in `Local State`, strip the 5-byte `DPAPI` prefix, `CryptUnprotectData` via `pywin32`.

## Value formats handled

Chromium cookie values are version-tagged. The tool sniffs the prefix and dispatches to the right cipher:

- **v10 / v11** (legacy) — AES-CBC, key derived from local salt + PBKDF2 fixed iteration count.
- **v80 / v20** (current) — AES-256-GCM. Format: `"v80" + 12-byte nonce + ciphertext + 16-byte tag`, unwrapped DPAPI key used directly.

Chrome also prepends a 32-byte SHA-256-of-host-key prefix to each decrypted value (defense against cross-host cookie swapping). The strip path tries to UTF-8-decode the tail; if that fails, fall back to the full payload — older v10 rows do not carry the prefix.

## Output formats

- `json` (default) — structured dump.
- `netscape` — `cookies.txt` for `curl --cookie-jar` / `wget --load-cookies`.
- `import` — write directly into another browser's `Cookies` SQLite (session migration across machines / browsers).

## Usage

```bash
python -m browser_cookies_cli chrome --host example.com
python -m browser_cookies_cli firefox --format netscape -o cookies.txt
python -m browser_cookies_cli brave --import-into chrome
```

Pre-flight detects the browser version via `<browser> --version` so every export is tagged with the exact build — useful when Chrome ships a new key format in a minor release and decrypts start failing.

## Repository layout

```
browser_cookies_cli/
├── browser_cookies_cli/
│   ├── __main__.py       # CLI entrypoint
│   ├── chromium.py       # Chrome/Brave/Chromium/Edge decrypt path
│   ├── firefox.py        # Firefox (no encryption) path
│   ├── crypto.py         # AES-CBC / AES-GCM / DPAPI / Keychain / SecretService
│   └── formats.py        # JSON / Netscape / import writers
├── tests/                # Unit, integration, E2E (Ubuntu + macOS + Windows matrix)
├── build/build_portable.py  # Portable single-file build script
└── .github/workflows/    # CI: test matrix + portable build on tag
```

## Platform notes

- **Linux**: GNOME Keyring / KWallet must be unlocked. If you are logged into the desktop session, it already is.
- **macOS**: First run triggers a Keychain-unlock prompt if the login keychain is locked.
- **Windows**: `pywin32` required. Closed-browser runs are cleaner — the live `Cookies` SQLite is locked.

## What this tool is not

- **Not a cookie stealer for other users.** It runs as the logged-in user whose keyring / keychain / DPAPI holds the key. On a single-user machine this is not a bypass; it is surfacing data you already control.
- **Not an exploit.** Chromium's `os_crypt` protects cookies from other users, not from the user themselves. This tool is the "user themselves" path, done right.
