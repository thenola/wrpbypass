#!/usr/bin/env bash

# Build self-contained Linux executable for wrpbypass_deb.py
# Use this INSIDE Debian/Ubuntu (e.g. Live USB), after unpacking wrpbypass_debian.zip.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v pyinstaller >/dev/null 2>&1; then
  echo "[!] pyinstaller not found. Install with:  python3 -m pip install pyinstaller"
  exit 1
fi

echo "[*] Building Linux executable from wrpbypass_deb.py..."
pyinstaller -F wrpbypass_deb.py --name wrpbypass_deb --distpath dist_debian

echo "[+] Done. Resulting binary: dist_debian/wrpbypass_deb"