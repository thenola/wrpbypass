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
    """
    Ensure we run as root on Unix-like systems.
    On Windows, this script is not supported and will exit with a message.
    """
    # On Windows there is no geteuid – this tool is meant for Linux.
    if not hasattr(os, "geteuid"):
        print("[!] wrpbypass_deb.py is intended to run on Linux (Debian/Ubuntu Live).")
        print("[!] Please boot a Linux live environment and run it there as root.")
        sys.exit(1)

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


def _run_with_args(args: argparse.Namespace) -> int:
    """Core logic shared between CLI and interactive modes."""
    ensure_root()

    mountpoint = None
    try:
        mountpoint = mount_partition(args.device, args.mountpoint)

        if args.mode == "install":
            if not args.wrpbypass_exe:
                print("[!] In install mode you must pass --wrpbypass-exe /path/to/wrpbypass.exe")
                return 1
            backup_and_replace_utilman(
                mountpoint, args.wrpbypass_exe, dry_run=getattr(args, "dry_run", False)
            )
        elif args.mode == "restore":
            restore_files(mountpoint, dry_run=getattr(args, "dry_run", False))
        return 0
    finally:
        # Path.is_mount() не существует, используем os.path.ismount
        if mountpoint and os.path.ismount(str(mountpoint)):
            try:
                umount_partition(mountpoint)
            except Exception as e:
                print(f"[!] Ошибка размонтирования: {e}")


def _list_partitions() -> list[tuple[str, str, str, str]]:
    """
    Return a list of (device, size, fstype, mountpoint) using lsblk.
    Falls back to empty list if lsblk is not available.
    """
    parts: list[tuple[str, str, str, str]] = []
    try:
        cp = subprocess.run(
            ["lsblk", "-o", "NAME,SIZE,FSTYPE,MOUNTPOINT", "-rn"],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return parts

    for line in cp.stdout.splitlines():
        cols = line.split()
        if not cols:
            continue
        name = cols[0]
        size = cols[1] if len(cols) > 1 else "?"
        fstype = cols[2] if len(cols) > 2 else ""
        mount = cols[3] if len(cols) > 3 else ""
        dev = f"/dev/{name}"
        parts.append((dev, size, fstype, mount))
    return parts


def interactive() -> int:
    """Interactive helper (replaces pydeb.sh logic) for Debian/Ubuntu Live."""
    script_dir = Path(__file__).resolve().parent

    print("=== wrpbypass helper for Debian/Ubuntu Live ===")
    print()
    print("[i] Available disks/partitions:")
    parts = _list_partitions()
    if parts:
        for idx, (dev, size, fstype, mount) in enumerate(parts, start=1):
            print(
                f"  {idx}) {dev:12} {size:>8}  {fstype or '-':8}  {mount or '-'}"
            )
    else:
        print("[!] lsblk not found or no partitions detected. You will need to type the device path manually.")

    print()
    raw = input(
        "Select partition number or enter device path (e.g. /dev/sda1): "
    ).strip()
    if not raw:
        print("[!] Device is empty, aborting.")
        return 1

    if raw.isdigit() and parts:
        idx = int(raw)
        if 1 <= idx <= len(parts):
            device = parts[idx - 1][0]
        else:
            print("[!] Invalid number, aborting.")
            return 1
    else:
        device = raw

    print()
    print("Select mode:")
    print("  1) Install hook (replace Utilman.exe with wrpbypass.exe)")
    print("  2) Restore original Utilman.exe from backup")
    choice = input("Choice [1/2]: ").strip()

    if choice == "1":
        mode = "install"
    elif choice == "2":
        mode = "restore"
    else:
        print("[!] Invalid choice. Use 1 or 2.")
        return 1

    mountpoint = "/mnt/win"
    wrp_exe = None

    if mode == "install":
        print()
        default_wrp = script_dir / "dist" / "Utilman.exe"
        if default_wrp.is_file():
            print(f"Found built Utilman.exe at: {default_wrp}")
            use_default = input("Use this path? [Y/n]: ").strip() or "Y"
            if use_default.lower().startswith("y"):
                wrp_exe = str(default_wrp)

        if not wrp_exe:
            print(
                "You must provide path to Utilman.exe (built from wrpbypass.py), "
                "e.g. /media/usb/dist/Utilman.exe"
            )
            wrp_exe = input("Path to Utilman.exe: ").strip()

        if not wrp_exe or not Path(wrp_exe).is_file():
            print("[!] Utilman.exe not found at given path.")
            return 1

    args = argparse.Namespace(
        device=device,
        mountpoint=mountpoint,
        mode=mode,
        wrpbypass_exe=wrp_exe,
        dry_run=False,
    )

    return _run_with_args(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="wrpbypass_linux: replace/restore Utilman.exe on a Windows partition"
    )
    parser.add_argument(
        "--device",
        required=True,
        help="Windows partition device (e.g. /dev/sda1)",
    )
    parser.add_argument(
        "--mountpoint",
        default="/mnt/win",
        help="Mount point (default: /mnt/win)",
    )
    parser.add_argument(
        "--mode",
        choices=["install", "restore"],
        required=True,
        help="Mode: install (replace) or restore (restore original files)",
    )
    parser.add_argument(
        "--wrpbypass-exe",
        help=(
            "Path to wrpbypass.exe (required in install mode, "
            "e.g. /media/usb/dist/wrpbypass.exe)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without modifying any files",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """
    Two modes:
    - CLI: arguments provided (backward compatible)
    - Interactive: no arguments (replaces pydeb.sh)
    """
    # Guard against accidental execution on Windows.
    if os.name == "nt":
        print("[!] wrpbypass_deb.py is a Linux-only helper (Debian/Ubuntu Live).")
        print("[!] For Windows, use wrpbypass.exe / Utilman.exe build instead.")
        return 1

    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        return interactive()

    parser = build_parser()
    args = parser.parse_args(argv)
    return _run_with_args(args)


if __name__ == "__main__":
    raise SystemExit(main())

