#!/usr/bin/env bash

# Quick helper script for Debian-based Live systems
# to install or restore winre on a Windows partition.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WINRE_LINUX="${SCRIPT_DIR}/winre_linux.py"

if [[ ! -f "$WINRE_LINUX" ]]; then
  echo "[!] winre_linux.py not found in ${SCRIPT_DIR}"
  exit 1
fi

# Устанавливаем правильные права на выполнение
echo "[+] Setting execute permissions on winre_linux.py"
chmod 755 "$WINRE_LINUX"

echo "=== wrpbypass helper for Debian/Ubuntu Live ==="
echo
echo "[i] Available disks/partitions:"
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
echo

read -rp "Windows partition device (e.g. /dev/sda1): " DEVICE
if [[ -z "${DEVICE}" ]]; then
  echo "[!] Device is empty, aborting."
  exit 1
fi

echo
echo "Select mode:"
echo "  1) Install hook (replace Utilman.exe with wrpbypass.exe)"
echo "  2) Restore original Utilman.exe from backup"
read -rp "Choice [1/2]: " CHOICE

case "$CHOICE" in
  1) MODE="install" ;;
  2) MODE="restore" ;;
  *)
    echo "[!] Invalid choice. Use 1 or 2."
    exit 1
    ;;
esac

MOUNTPOINT="/mnt/win"

if [[ "$MODE" == "install" ]]; then
  echo
  DEFAULT_WRP_EXE="${SCRIPT_DIR}/dist/wrpbypass.exe"
  if [[ -f "$DEFAULT_WRP_EXE" ]]; then
    echo "Found built wrpbypass.exe at: $DEFAULT_WRP_EXE"
    read -rp "Use this path? [Y/n]: " USE_DEFAULT
    USE_DEFAULT=${USE_DEFAULT:-Y}
    if [[ "$USE_DEFAULT" =~ ^[Yy]$ ]]; then
      WINRE_EXE="$DEFAULT_WRP_EXE"
    fi
  fi

  if [[ -z "${WINRE_EXE:-}" ]]; then
    echo "You must provide path to wrpbypass.exe (built from wrpbypass.py), e.g. /media/usb/dist/wrpbypass.exe"
    read -rp "Path to winre.exe: " WINRE_EXE
  fi

  if [[ -z "${WINRE_EXE}" || ! -f "${WINRE_EXE}" ]]; then
    echo "[!] wrpbypass.exe not found at given path."
    exit 1
  fi

  sudo python3 "$WINRE_LINUX" \
    --device "$DEVICE" \
    --mountpoint "$MOUNTPOINT" \
    --mode install \
    --wrpbypass-exe "$WINRE_EXE"
else
  sudo python3 "$WINRE_LINUX" \
    --device "$DEVICE" \
    --mountpoint "$MOUNTPOINT" \
    --mode restore
fi

echo
echo "[+] Done."