#!/bin/bash

set -e

APP_NAME="wrpbypass_deb"
SERVICE_NAME="wrpbypass"
INSTALL_DIR="/opt/wrpbypass"

echo "[*] Checking root privileges..."

if [ "$EUID" -ne 0 ]; then
echo "Run this script as root."
exit 1
fi

echo "[*] Checking application file..."

if [ ! -f "./$APP_NAME" ]; then
echo "File $APP_NAME not found in current directory."
exit 1
fi

echo "[*] Detecting live USB device..."

LIVE_DEV=$(findmnt -no SOURCE /run/live/medium 2>/dev/null || true)

if [ -z "$LIVE_DEV" ]; then
echo "Cannot detect live USB device."
exit 1
fi

USB_DEV=$(lsblk -no PKNAME "$LIVE_DEV")
USB_DEV="/dev/$USB_DEV"

echo "[+] Live USB detected: $USB_DEV"

echo "[*] Checking for existing persistence partition..."

PERSIST_DEV=$(blkid -L persistence || true)

if [ -z "$PERSIST_DEV" ]; then
echo "[*] Creating persistence partition..."

```
PART_NUM=$(lsblk -ln "$USB_DEV" | wc -l)
NEXT_PART=$((PART_NUM))

parted -s "$USB_DEV" mkpart primary ext4 70% 100%
partprobe "$USB_DEV"

sleep 2

PERSIST_DEV="${USB_DEV}${NEXT_PART}"

echo "[*] Formatting persistence partition..."
mkfs.ext4 -L persistence "$PERSIST_DEV"
```

fi

echo "[*] Configuring persistence..."

mkdir -p /mnt/persistence
mount "$PERSIST_DEV" /mnt/persistence

echo "/ union" > /mnt/persistence/persistence.conf

umount /mnt/persistence

echo "[*] Installing application..."

mkdir -p "$INSTALL_DIR"
cp "./$APP_NAME" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/$APP_NAME"

echo "[*] Creating systemd service..."

cat > /etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=WRP Bypass Autostart
After=network.target

[Service]
Type=simple
ExecStart=${INSTALL_DIR}/${APP_NAME}
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo
echo "Setup finished successfully."
echo "Boot using: Live system (persistence)"
