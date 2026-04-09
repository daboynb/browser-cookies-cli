#!/usr/bin/env bash
set -euo pipefail

echo "=== Setting up test environment ==="

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
mkdir -p "$XDG_RUNTIME_DIR"

# Virtual display for gnome-keyring's GTK prompter
Xvfb :99 -screen 0 1024x768x24 &>/dev/null &
export DISPLAY=:99

exec dbus-run-session -- bash -c '
set -euo pipefail
export XDG_RUNTIME_DIR="'"$XDG_RUNTIME_DIR"'"
export DISPLAY=:99

# Start gnome-keyring-daemon
eval "$(echo "" | gnome-keyring-daemon --start --unlock --components=secrets 2>/dev/null)" || true

# Auto-accept any keyring creation dialog (press Enter repeatedly)
(
    for i in $(seq 1 15); do
        sleep 1
        xdotool key Return 2>/dev/null || true
    done
) &
ACCEPTER=$!

# Create Chrome profile + keyring entry
python3 browser_cookies_cli/tests/setup_chrome.py && echo "[+] Chrome profile initialized" || echo "[-] Chrome setup failed"

# Stop dialog handler
kill $ACCEPTER 2>/dev/null || true

# Create Firefox profile
python3 browser_cookies_cli/tests/setup_firefox.py
echo "[+] Firefox profile initialized"

echo ""
echo "=== Running integration tests ==="
python3 browser_cookies_cli/tests/test_integration.py -v

echo ""
echo "=== Running end-to-end test ==="
python3 browser_cookies_cli/tests/test_e2e.py -v
'
