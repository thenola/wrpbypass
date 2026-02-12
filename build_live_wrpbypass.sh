#!/usr/bin/env bash

# Build a custom Debian Live ISO that auto-starts wrpbypass_deb at boot.
# Usage (run on Linux as root):
#   ./build_live_wrpbypass.sh debian-live-13.3.0-amd64-standard.iso ./wrpbypass_deb
#
# Requires: squashfs-tools, xorriso, rsync

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "[!] Run this script as root (sudo)."
  exit 1
fi

ISO_IN=${1:-debian-live-13.3.0-amd64-standard.iso}
WRP_BIN=${2:-./wrpbypass_deb}
ISO_OUT=${3:-debian-live-13.3.0-amd64-wrpbypass.iso}

if [[ ! -f "$ISO_IN" ]]; then
  echo "[!] Input ISO not found: $ISO_IN"
  exit 1
fi

if [[ ! -f "$WRP_BIN" ]]; then
  echo "[!] Compiled wrpbypass_deb binary not found: $WRP_BIN"
  echo "    Build it first with: pyinstaller -F wrpbypass_deb.py --name wrpbypass_deb"
  exit 1
fi

for cmd in unsquashfs mksquashfs xorriso rsync; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "[!] Required tool '$cmd' not found. Install 'squashfs-tools', 'xorriso', 'rsync'."
    exit 1
  fi
done

WORKDIR=$(mktemp -d -t wrpbypass_live_XXXX)
ISO_DIR="$WORKDIR/iso"
MNT="$WORKDIR/mnt"
SQUASH_DIR="$WORKDIR/squashfs-root"

echo "[*] Working directory: $WORKDIR"
mkdir -p "$ISO_DIR" "$MNT"

echo "[*] Mounting original ISO..."
mount -o loop "$ISO_IN" "$MNT"

echo "[*] Copying ISO contents..."
rsync -aH --exclude=/live/filesystem.squashfs "$MNT/" "$ISO_DIR/"
cp "$MNT/live/filesystem.squashfs" "$ISO_DIR/live/filesystem.squashfs"

umount "$MNT"
rmdir "$MNT"

echo "[*] Unpacking SquashFS..."
unsquashfs -d "$SQUASH_DIR" "$ISO_DIR/live/filesystem.squashfs"

echo "[*] Installing wrpbypass_deb into live system..."
install -D -m 755 "$WRP_BIN" "$SQUASH_DIR/usr/local/sbin/wrpbypass_deb"

SERVICE_DIR="$SQUASH_DIR/etc/systemd/system"
mkdir -p "$SERVICE_DIR" "$SQUASH_DIR/etc/systemd/system/multi-user.target.wants"

SERVICE_FILE="$SERVICE_DIR/wrpbypass-deb.service"
cat > "$SERVICE_FILE" <<'EOF'
[Unit]
Description=wrpbypass_deb auto-run at boot
After=multi-user.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/wrpbypass_deb
StandardInput=tty
StandardOutput=journal+console
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

ln -sf "../wrpbypass-deb.service" \
  "$SQUASH_DIR/etc/systemd/system/multi-user.target.wants/wrpbypass-deb.service"

echo "[*] Repacking SquashFS..."
mv "$ISO_DIR/live/filesystem.squashfs" "$ISO_DIR/live/filesystem.squashfs.orig"
mksquashfs "$SQUASH_DIR" "$ISO_DIR/live/filesystem.squashfs" -noappend

echo "[*] Building new ISO..."
xorriso -as mkisofs \
  -r -V "DEBIAN_LIVE_WRPBYPASS" \
  -o "$ISO_OUT" \
  -J -joliet-long -cache-inodes \
  -isohybrid-mbr /usr/lib/ISOLINUX/isohdpfx.bin \
  -c isolinux/boot.cat \
  -b isolinux/isolinux.bin \
     -no-emul-boot -boot-load-size 4 -boot-info-table \
  "$ISO_DIR"

echo "[+] Done."
echo "[+] New ISO: $ISO_OUT"
echo "[+] You can now write it to a USB stick (e.g. with 'dd' or Rufus)."

rm -rf "$WORKDIR"

