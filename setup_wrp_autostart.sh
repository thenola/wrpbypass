#!/bin/bash

set -e

APP_NAME="wrpbypass_deb"
SERVICE_NAME="wrpbypass"
INSTALL_DIR="/opt/wrpbypass"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "[*] Checking for root privileges..."

if [ "$EUID" -ne 0 ]; then
echo "Please run this script as root or with sudo."
exit 1
fi

echo "[*] Searching for persistence partition..."

PERSIST_DEV=$(blkid -L persistence || true)

if [ -z "$PERSIST_DEV" ]; then
echo "[!] Persistence partition not found."
echo "Create a partition labeled 'persistence' and reboot into Live with persistence."
exit 1
fi

echo "[+] Found persistence partition: $PERSIST_DEV"

echo "[*] Verifying persistence.conf..."

mkdir -p /mnt/persistence
mount "$PERSIST_DEV" /mnt/persistence || true

if [ ! -f /mnt/persistence/persistence.conf ]; then
echo "[*] Creating persistence.conf..."
echo "/ union" > /mnt/persistence/persistence.conf
fi

umount /mnt/persistence

echo "[*] Installing application..."

if [ ! -f "./$APP_NAME" ]; then
echo "[!] File $APP_NAME not found in the current directory."
exit 1
fi

mkdir -p "$INSTALL_DIR"
cp "./$APP_NAME" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/$APP_NAME"

echo "[*] Creating systemd service..."

cat > "$SERVICE_FILE" <<EOF
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

echo "[*] Enabling service..."

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo
echo "Setup complete."
echo "On boot, select 'Live system (persistence)' or add the 'persistence' boot parameter."
