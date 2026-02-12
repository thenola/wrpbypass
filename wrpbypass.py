import argparse
import csv
import json
import subprocess
import sys
import os
from pathlib import Path
from typing import List
from datetime import datetime
import platform
import getpass

import ctypes
from prompt_toolkit import prompt
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.styles import Style


VERSION = "1.3"
GITHUB = "thenola/wrpbypass"


def _detect_data_dir() -> Path:
    """
    Choose a writable directory for config/logs.

    Priority:
    1) WRP_DIR environment variable
    2) If running from System32 -> C:\\ProgramData\\wrpbypass
    3) Otherwise: <script_dir>\\data
    """
    env = os.environ.get("WRP_DIR")
    if env:
        p = Path(env)
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p
        except Exception:
            pass

    try:
        if getattr(sys, "frozen", False):
            here = Path(sys.executable).resolve().parent
        else:
            here = Path(__file__).resolve().parent
    except Exception:
        here = Path.cwd()

    system_root = Path(os.environ.get("SystemRoot", r"C:\\Windows"))
    system32 = system_root / "System32"

    try:
        if here.samefile(system32):
            base = Path(os.environ.get("SystemDrive", "C:")) / "ProgramData" / "wrpbypass"
        else:
            base = here / "data"
    except Exception:
        base = here / "data"

    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:
        base = Path.cwd()

    return base


DATA_DIR = _detect_data_dir()
CONFIG_PATH = DATA_DIR / "config.yml"
LOG_FILE = DATA_DIR / "wrpbypass.log"

KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
MOVEFILE_DELAY_UNTIL_REBOOT = 0x00000004

_DEFAULT_STYLE_DICT = {
    # base colors
    "info": "ansiblue",
    "error": "bold ansired",
    "warn": "ansiyellow",
    "ok": "ansigreen",
    # menu-specific accents
    "menu-number": "bold #00bfff",
    "menu-text": "#cccccc",
    "menu-danger": "bold #ff6b6b",
    "menu-warn": "bold #ffd93d",
    "menu-highlight": "bold #00bfff bg:#2d5a7a",
    # logo
    "logo-main": "bold italic #00bfff",
    "logo-meta": "italic #6c8c9f",
    # status indicators
    "status-online": "bold #51cf66",
    "status-offline": "bold #ff6b6b",
    "status-busy": "bold #ffd93d",
    # borders and decorations
    "border": "#4a6fa5",
    "border-soft": "#2d5a7a",
}

_NO_COLOR_STYLE_DICT = {k: "" for k in _DEFAULT_STYLE_DICT.keys()}

style = Style.from_dict(_DEFAULT_STYLE_DICT)


def _str_to_bool(value: str, default: bool = True) -> bool:
    v = (value or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def configure_style(use_color: bool) -> None:
    """Rebuild global style with or without colors."""
    global style
    style_dict = _DEFAULT_STYLE_DICT if use_color else _NO_COLOR_STYLE_DICT
    style = Style.from_dict(style_dict)


def info(text: str) -> None:
    print_formatted_text(HTML(f"<info>{text}</info>"), style=style)


def ok(text: str) -> None:
    print_formatted_text(HTML(f"<ok>{text}</ok>"), style=style)


def warn(text: str) -> None:
    print_formatted_text(HTML(f"<warn>{text}</warn>"), style=style)


def error(text: str) -> None:
    print_formatted_text(HTML(f"<error>{text}</error>"), style=style, file=sys.stderr)


def log_action(action: str) -> None:
    """Append simple timestamped entry to wrpbypass.log (best-effort)."""
    try:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {action}\n")
    except Exception:
        # Logging must never break main functionality
        pass


def _load_config() -> dict:
    """Load simple key: value config from CONFIG_PATH (YAML-like, no extra deps)."""
    cfg: dict[str, str] = {}
    if not CONFIG_PATH.is_file():
        return cfg
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        log_action(f"Failed to read config.yml: {e!r}")
        return cfg

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        cfg[key.strip().lower()] = val.strip()
    return cfg


def _ensure_default_config() -> None:
    """Create minimal config.yml if missing."""
    if CONFIG_PATH.exists():
        return
    content = (
        "# wrpbypass configuration\n"
        "# color: true|false (default: true)\n"
        "color: true\n"
    )
    try:
        CONFIG_PATH.write_text(content, encoding="utf-8")
    except Exception as e:
        log_action(f"Failed to write default config.yml: {e!r}")


def ask(label: str) -> str:
    """Prompt user for input with basic styling."""
    return prompt(HTML(f"<u><b><info>{label}</info></b></u>&gt; ")).strip()

def pause(label: str) -> str:
    """Prompt user for input with basic styling."""
    return prompt(HTML(f"\n&lt;<u><b><info>back</info></b></u> ")).strip()

def clear_screen() -> None:
    """Clear the console screen (cls on Windows, clear on others)."""
    os.system("cls" if os.name == "nt" else "clear")


def _get_system32() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\\Windows")) / "System32"


def movefile_ex(src: str, dst: str | None) -> None:
    """Schedule rename/move on next reboot."""
    src_w = ctypes.c_wchar_p(src)
    dst_w = ctypes.c_wchar_p(dst) if dst is not None else None
    res = KERNEL32.MoveFileExW(src_w, dst_w, MOVEFILE_DELAY_UNTIL_REBOOT)
    if not res:
        err = ctypes.get_last_error()
        raise ctypes.WinError(err)


def schedule_restore_utilman():
    """
    Schedule restore:
    - C:\\Windows\\System32\\Utilman.exe.tmp -> Utilman.exe
    - optionally remove current Utilman.exe and wrpbypass.exe copy if present
    NOTE: runs on next reboot.
    """
    system32 = _get_system32()
    utilman = system32 / "Utilman.exe"
    utilman_backup = system32 / "Utilman.exe.tmp"
    wrp_exe = system32 / "wrpbypass.exe"

    if not utilman_backup.exists():
        error(f"Backup file not found: {utilman_backup}")
        return

    info("Scheduling Utilman.exe restore on next reboot...")

    try:
        # 1) Schedule current Utilman.exe removal on reboot (dst=None).
        if utilman.exists():
            info(f"  - Current {utilman} will be deleted on reboot.")
            movefile_ex(str(utilman), None)

        # 2) Rename backup back to Utilman.exe
        info(f"  - {utilman_backup} will be renamed to {utilman} on reboot.")
        movefile_ex(str(utilman_backup), str(utilman))

        # 3) Optionally delete standalone wrpbypass.exe
        if wrp_exe.exists():
            info(f"  - {wrp_exe} will be deleted on reboot.")
            movefile_ex(str(wrp_exe), None)

        ok("Now reboot the computer to complete Utilman.exe restore.")
    except Exception as e:
        error(f"Error while scheduling restore: {e}")


def install_utilman_hook():
    """
    Backup Utilman.exe and replace it with wrpbypass.exe (this program),
    so Ease of Access button launches our tool.
    """
    system32 = _get_system32()
    utilman = system32 / "Utilman.exe"
    utilman_backup = system32 / "Utilman.exe.tmp"

    # Detect path to current executable/script.
    if getattr(sys, "frozen", False):
        wrp_src = Path(sys.executable)
    else:
        wrp_src = Path(__file__).resolve()

    wrp_dst = system32 / "wrpbypass.exe"

    info(f"System32: {system32}")

    if not utilman.exists():
        error(f"{utilman} not found. Cannot install hook.")
        return

    # Backup Utilman.exe if needed.
    if utilman_backup.exists():
        warn("Backup Utilman.exe.tmp already exists. Skipping backup.")
    else:
        try:
            info(f"Renaming {utilman} -> {utilman_backup} (backup).")
            utilman.rename(utilman_backup)
        except Exception as e:
            error(f"Failed to backup Utilman.exe: {e}")
            return

    # Copy wrpbypass.exe into System32 if needed.
    try:
        if wrp_src.resolve() != wrp_dst.resolve():
            info(f"Copying {wrp_src} -> {wrp_dst}")
            result = subprocess.run(
                ["cmd", "/c", "copy", "/Y", str(wrp_src), str(wrp_dst)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                error(
                    f"Failed to copy wrpbypass.exe (exit {result.returncode}): {result.stderr.strip()}"
                )
                return
        else:
            info("wrpbypass.exe is already in System32.")
    except Exception as e:
        error(f"Failed to copy wrpbypass.exe: {e}")
        return

    # Replace Utilman.exe with wrpbypass.exe.
    try:
        if utilman.exists():
            info(f"Removing current {utilman}.")
            try:
                utilman.unlink()
            except PermissionError as e:
                error(f"Cannot remove {utilman} (in use?): {e}")
                return

        info(f"Renaming {wrp_dst} -> {utilman}")
        wrp_dst.rename(utilman)

        ok(
            "Hook installed. On the Windows logon screen, press the Ease of Access button to start wrpbypass."
        )
    except Exception as e:
        error(f"Failed to replace Utilman.exe: {e}")


def restore_utilman_now():
    """
    Try to restore Utilman.exe immediately (without scheduling).
    If files are locked (e.g. current process is Utilman.exe),
    suggest using scheduled restore instead.
    """
    system32 = _get_system32()
    utilman = system32 / "Utilman.exe"
    utilman_backup = system32 / "Utilman.exe.tmp"
    wrp_exe = system32 / "wrpbypass.exe"

    if getattr(sys, "frozen", False):
        current_path = Path(sys.executable)
    else:
        current_path = Path(__file__).resolve()

    if not utilman_backup.exists():
        error("Backup Utilman.exe.tmp not found. Nothing to restore.")
        return

    info("Trying to restore Utilman.exe immediately...")

    # If current process is Utilman.exe, direct restore is dangerous/impossible.
    try:
        if utilman.exists() and utilman.resolve() == current_path.resolve():
            warn(
                "Current process is Utilman.exe; cannot safely replace the file while it is running."
            )
            warn(
                "Use the scheduled restore option (after reboot) instead."
            )
            return
    except Exception:
        # If resolution fails, continue with best effort.
        pass

    # Remove current Utilman.exe if it's not the backup.
    if utilman.exists() and utilman != utilman_backup:
        try:
            info(f"Removing current {utilman}.")
            utilman.unlink()
        except PermissionError as e:
            error(f"Cannot remove {utilman} (probably in use): {e}")
            warn(
                "Use the scheduled restore option (after reboot) instead."
            )
            return

    # Optionally remove standalone wrpbypass.exe.
    if wrp_exe.exists():
        try:
            info(f"Removing {wrp_exe}.")
            wrp_exe.unlink()
        except Exception as e:
            warn(f"Failed to remove {wrp_exe}: {e}. Continuing restore.")

    try:
        info(f"Restoring {utilman_backup} -> {utilman}")
        utilman_backup.rename(utilman)
        ok("Utilman.exe restored successfully.")
    except Exception as e:
        error(f"Failed to restore Utilman.exe: {e}")


# Try to set UTF-8 for Python output.
for _stream in ("stdout", "stderr"):
    stream = getattr(sys, _stream, None)
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def run_command(args: List[str]) -> int:
    """Run a Windows command (e.g., net) and print output (cp866 for Russian consoles)."""
    try:
        completed = subprocess.run(
            args,
            text=True,
            capture_output=True,
            shell=False,
            encoding="cp866",
            errors="replace",
        )
    except FileNotFoundError:
        error("Command 'net' not found on this system.")
        return 1

    if completed.stdout:
        print(completed.stdout.strip())
    if completed.stderr:
        print(completed.stderr.strip(), file=sys.stderr)

    return completed.returncode


def capture_output(args: List[str]) -> subprocess.CompletedProcess[str] | None:
    """Run a command and return CompletedProcess without printing."""
    try:
        completed = subprocess.run(
            args,
            text=True,
            capture_output=True,
            shell=False,
            encoding="cp866",
            errors="replace",
        )
    except FileNotFoundError:
        error("Command 'net' not found on this system.")
        return None

    if completed.returncode != 0 and completed.stderr:
        print(completed.stderr.strip(), file=sys.stderr)

    return completed


def cmd_user_list(args: argparse.Namespace) -> int:
    cmd = ["net", "user"]
    if getattr(args, "domain", False):
        cmd.append("/domain")
    return run_command(cmd)


def _get_all_usernames(domain: bool = False) -> List[str]:
    """Get list of users (local or domain)."""
    base_cmd: List[str] = ["net", "user"]
    if domain:
        base_cmd.append("/domain")

    completed = capture_output(base_cmd)
    if not completed or not completed.stdout:
        return []

    users: List[str] = []
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        low = line.lower()
        if (
            set(line) <= {"-", " "}
            or "account" in low
            or "учетные записи" in low
            or "команда выполнена успешно" in low
            or "command completed successfully" in low
        ):
            continue
        users.extend(part for part in line.split() if part)

    return users


def cmd_user_export(args: argparse.Namespace) -> int:
    """Export user list to CSV or JSON."""
    users = _get_all_usernames(domain=getattr(args, "domain", False))
    if not users:
        error("Failed to get user list.")
        return 1

    out_path = Path(args.path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = args.format.lower()
    if fmt == "csv":
        with out_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["username"])
            for name in users:
                writer.writerow([name])
    elif fmt == "json":
        with out_path.open("w", encoding="utf-8") as f:
            json.dump({"users": users}, f, ensure_ascii=False, indent=2)
    else:
        error(f"Unknown format: {fmt}")
        return 1

    ok(f"Exported users: {len(users)} -> {out_path}")
    return 0


def cmd_user_search(args: argparse.Namespace) -> int:
    """Search users by substring (case-insensitive)."""
    users = _get_all_usernames(domain=getattr(args, "domain", False))
    pattern = args.pattern.lower()
    matched = [u for u in users if pattern in u.lower()]

    if not matched:
        warn("No matches found.")
        return 0

    info("Matched users:")
    for name in matched:
        print(f"  {name}")
    return 0


def cmd_user_bulk_add(args: argparse.Namespace) -> int:
    """Bulk create users from CSV (username,password,optional fullname,active)."""
    path = Path(args.file)
    if not path.is_file():
        error(f"File not found: {path}")
        return 1

    created = 0
    failed = 0

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=args.delimiter)
        required_fields = {"username", "password"}
        missing = required_fields - set(reader.fieldnames or [])
        if missing:
            error(
                "CSV must contain columns: username, password "
                "(optional: fullname, active)."
            )
            return 1

        for row in reader:
            username = (row.get("username") or "").strip()
            password = (row.get("password") or "").strip()
            fullname = (row.get("fullname") or "").strip() or None
            active_raw = (row.get("active") or "").strip().lower()
            if not username or not password:
                continue

            active_val = None
            if active_raw in ("yes", "no"):
                active_val = active_raw == "yes"

            ns = argparse.Namespace(
                username=username,
                password=password,
                fullname=fullname,
                active=active_val,
            )
            rc = cmd_user_add(ns)
            if rc == 0:
                created += 1
            else:
                failed += 1

    info(f"Created users: {created}, errors: {failed}")
    return 0 if failed == 0 else 1


def cmd_user_show(args: argparse.Namespace) -> int:
    cmd = ["net", "user", args.username]
    if getattr(args, "domain", False):
        cmd.append("/domain")
    return run_command(cmd)


def cmd_user_add(args: argparse.Namespace) -> int:
    cmd = ["net", "user", args.username, args.password, "/add"]
    if args.fullname:
        cmd.append(f'/fullname:"{args.fullname}"')
    if args.active is not None:
        cmd += ["/active:" + ("yes" if args.active else "no")]
    return run_command(cmd)


def cmd_user_delete(args: argparse.Namespace) -> int:
    return run_command(["net", "user", args.username, "/delete"])


def cmd_user_enable(args: argparse.Namespace) -> int:
    return run_command(["net", "user", args.username, "/active:yes"])


def cmd_user_disable(args: argparse.Namespace) -> int:
    return run_command(["net", "user", args.username, "/active:no"])


def cmd_user_set_password(args: argparse.Namespace) -> int:
    return run_command(["net", "user", args.username, args.password])


def cmd_user_set_expiry(args: argparse.Namespace) -> int:
    """Set account expiration date or remove restriction."""
    return run_command(["net", "user", args.username, f"/expires:{args.expires}"])


def cmd_user_require_password(args: argparse.Namespace) -> int:
    """Mark password as required or not required for login."""
    return run_command(
        [
            "net",
            "user",
            args.username,
            f"/passwordreq:{'yes' if args.required else 'no'}",
        ]
    )


def cmd_user_allow_password_change(args: argparse.Namespace) -> int:
    """Allow or deny user to change own password."""
    return run_command(
        [
            "net",
            "user",
            args.username,
            f"/passwordchg:{'yes' if args.allowed else 'no'}",
        ]
    )


def cmd_group_list(args: argparse.Namespace) -> int:
    """List local groups."""
    return run_command(["net", "localgroup"])


def cmd_group_show(args: argparse.Namespace) -> int:
    """Show local group details."""
    return run_command(["net", "localgroup", args.groupname])


def cmd_domain_group_list(args: argparse.Namespace) -> int:
    """List domain groups via `net group /domain`."""
    return run_command(["net", "group", "/domain"])


def cmd_domain_group_show(args: argparse.Namespace) -> int:
    """Show domain group details via `net group <name> /domain`."""
    return run_command(["net", "group", args.groupname, "/domain"])


def cmd_group_add(args: argparse.Namespace) -> int:
    return run_command(["net", "localgroup", args.groupname, "/add"])


def cmd_group_delete(args: argparse.Namespace) -> int:
    return run_command(["net", "localgroup", args.groupname, "/delete"])


def cmd_group_add_member(args: argparse.Namespace) -> int:
    return run_command(["net", "localgroup", args.groupname, args.username, "/add"])


def cmd_group_remove_member(args: argparse.Namespace) -> int:
    return run_command(
        ["net", "localgroup", args.groupname, args.username, "/delete"]
    )


def cmd_group_set_comment(args: argparse.Namespace) -> int:
    """Set comment/description for a local group."""
    return run_command(
        [
            "net",
            "localgroup",
            args.groupname,
            f'/comment:"{args.comment}"',
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wrpbypass",
        description="CLI tool for Windows local user and group administration.",
    )

    parser.add_argument(
        "--nocolor",
        action="store_true",
        help="Disable colored output (monochrome).",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # user subcommands
    user_parser = subparsers.add_parser(
        "user", help="Operations with local users."
    )
    user_sub = user_parser.add_subparsers(dest="user_cmd", required=True)

    user_list = user_sub.add_parser("list", help="List users.")
    user_list.add_argument(
        "--domain",
        action="store_true",
        help="Show domain users (net user /domain).",
    )
    user_list.set_defaults(func=cmd_user_list)

    user_export = user_sub.add_parser(
        "export",
        help=(
            "Export user list to CSV or JSON "
            "(extended wrpbypass feature)."
        ),
    )
    user_export.add_argument("path", help="Path to output file.")
    user_export.add_argument(
        "--format",
        "-f",
        default="csv",
        choices=["csv", "json"],
        help="Output format: csv or json (default: csv).",
    )
    user_export.add_argument(
        "--domain",
        action="store_true",
        help="Export domain users (net user /domain).",
    )
    user_export.set_defaults(func=cmd_user_export)

    user_search = user_sub.add_parser(
        "search",
        help=(
            "Search users by name substring "
            "(wrpbypass feature over `net user`)."
        ),
    )
    user_search.add_argument("pattern", help="Substring to search in username.")
    user_search.add_argument(
        "--domain",
        action="store_true",
        help="Search among domain users (net user /domain).",
    )
    user_search.set_defaults(func=cmd_user_search)

    user_bulk = user_sub.add_parser(
        "bulk-add",
        help=(
            "Bulk create users from CSV "
            "(not available in standard Windows tools)."
        ),
    )
    user_bulk.add_argument("file", help="Path to CSV file.")
    user_bulk.add_argument(
        "--delimiter",
        default=";",
        help="CSV delimiter (default: ';').",
    )
    user_bulk.set_defaults(func=cmd_user_bulk_add)

    user_show = user_sub.add_parser("show", help="Show user details.")
    user_show.add_argument("username", help="User name.")
    user_show.add_argument(
        "--domain",
        action="store_true",
        help="Show domain user info (net user /domain).",
    )
    user_show.set_defaults(func=cmd_user_show)

    user_add = user_sub.add_parser("add", help="Create user.")
    user_add.add_argument("username", help="User name.")
    user_add.add_argument("password", help="Password.")
    user_add.add_argument(
        "--fullname", help="Full name (comment).", default=None
    )
    user_add.add_argument(
        "--active",
        choices=["yes", "no"],
        help="Immediately enable or disable the account.",
    )
    user_add.set_defaults(
        func=lambda a: cmd_user_add(
            argparse.Namespace(
                username=a.username,
                password=a.password,
                fullname=a.fullname,
                active=None if a.active is None else a.active == "yes",
            )
        )
    )

    user_delete = user_sub.add_parser("delete", help="Delete user.")
    user_delete.add_argument("username", help="User name.")
    user_delete.set_defaults(func=cmd_user_delete)

    user_enable = user_sub.add_parser("enable", help="Enable account.")
    user_enable.add_argument("username", help="User name.")
    user_enable.set_defaults(func=cmd_user_enable)

    user_disable = user_sub.add_parser("disable", help="Disable account.")
    user_disable.add_argument("username", help="User name.")
    user_disable.set_defaults(func=cmd_user_disable)

    user_pass = user_sub.add_parser("set-password", help="Change password.")
    user_pass.add_argument("username", help="User name.")
    user_pass.add_argument("password", help="New password.")
    user_pass.set_defaults(func=cmd_user_set_password)

    user_expiry = user_sub.add_parser(
        "set-expiry",
        help=(
            "Set account expiration date. "
            "Use DD.MM.YYYY or 'never'."
        ),
    )
    user_expiry.add_argument("username", help="User name.")
    user_expiry.add_argument(
        "expires",
        help="Expiration date (DD.MM.YYYY) or 'never' to remove restriction.",
    )
    user_expiry.set_defaults(func=cmd_user_set_expiry)

    user_pwreq = user_sub.add_parser(
        "require-password",
        help="Make password required or not required for login.",
    )
    user_pwreq.add_argument("username", help="User name.")
    user_pwreq.add_argument(
        "required",
        choices=["yes", "no"],
        help="'yes' — password required, 'no' — not required.",
    )
    user_pwreq.set_defaults(
        func=lambda a: cmd_user_require_password(
            argparse.Namespace(username=a.username, required=a.required == "yes")
        )
    )

    user_pwchg = user_sub.add_parser(
        "allow-password-change",
        help="Allow or deny user to change own password.",
    )
    user_pwchg.add_argument("username", help="User name.")
    user_pwchg.add_argument(
        "allowed",
        choices=["yes", "no"],
        help="'yes' — user can change password, 'no' — cannot.",
    )
    user_pwchg.set_defaults(
        func=lambda a: cmd_user_allow_password_change(
            argparse.Namespace(username=a.username, allowed=a.allowed == "yes")
        )
    )

    # group subcommands
    group_parser = subparsers.add_parser(
        "group", help="Operations with local groups."
    )
    group_sub = group_parser.add_subparsers(dest="group_cmd", required=True)

    group_list = group_sub.add_parser("list", help="List local groups.")
    group_list.set_defaults(func=cmd_group_list)

    group_show = group_sub.add_parser("show", help="Show group details.")
    group_show.add_argument("groupname", help="Group name.")
    group_show.set_defaults(func=cmd_group_show)

    group_add = group_sub.add_parser("add", help="Create local group.")
    group_add.add_argument("groupname", help="Group name.")
    group_add.set_defaults(func=cmd_group_add)

    group_delete = group_sub.add_parser("delete", help="Delete local group.")
    group_delete.add_argument("groupname", help="Group name.")
    group_delete.set_defaults(func=cmd_group_delete)

    group_add_member = group_sub.add_parser(
        "add-member", help="Add user to group."
    )
    group_add_member.add_argument("groupname", help="Group name.")
    group_add_member.add_argument("username", help="User name.")
    group_add_member.set_defaults(func=cmd_group_add_member)

    group_remove_member = group_sub.add_parser(
        "remove-member", help="Remove user from group."
    )
    group_remove_member.add_argument("groupname", help="Group name.")
    group_remove_member.add_argument("username", help="User name.")
    group_remove_member.set_defaults(func=cmd_group_remove_member)

    group_comment = group_sub.add_parser(
        "set-comment", help="Set group comment/description."
    )
    group_comment.add_argument("groupname", help="Group name.")
    group_comment.add_argument("comment", help="Comment.")
    group_comment.set_defaults(func=cmd_group_set_comment)

    # Domain groups (read-only)
    domain_group_list = group_sub.add_parser(
        "domain-list",
        help="List domain groups (net group /domain, read-only).",
    )
    domain_group_list.set_defaults(func=cmd_domain_group_list)

    domain_group_show = group_sub.add_parser(
        "domain-show",
        help="Show domain group info (net group <name> /domain).",
    )
    domain_group_show.add_argument("groupname", help="Domain group name.")
    domain_group_show.set_defaults(func=cmd_domain_group_show)

    return parser


def main(argv: List[str] | None = None) -> int:
    """
    Two working modes:
    - CLI mode (with arguments) — full wrpbypass CLI.
    - Interactive menu (no arguments) — simple prompt-based workflow.
    Ctrl+C anywhere results in a clean exit without traceback.
    """
    try:
        if argv is None:
            argv = sys.argv[1:]

        # Ensure config.yml exists and read settings
        _ensure_default_config()
        cfg = _load_config()
        use_color = _str_to_bool(cfg.get("color", "true"), default=True)

        # Environment override: WRP_NOCOLOR=1 disables colors completely
        env_nc = os.environ.get("WRP_NOCOLOR")
        if env_nc is not None and _str_to_bool(env_nc, default=True):
            use_color = False

        # When compiled as Utilman.exe and launched from Windows logon screen,
        # the system may pass a "/debug" argument. In that case we ignore
        # the arguments and go straight to interactive menu.
        if argv and len(argv) == 1 and argv[0].lower().startswith("/debug"):
            log_action("Detected /debug argument from shell, switching to interactive menu")
            argv = []

        # If arguments are provided – keep the original CLI behavior.
        if argv:
            parser = build_parser()
            args = parser.parse_args(argv)

            if getattr(args, "nocolor", False):
                use_color = False

            configure_style(use_color)

            if not hasattr(args, "func"):
                parser.print_help()
                return 1

            rc = args.func(args)
            if rc == 5:
                error(
                    "Access denied. Run Command Prompt/PowerShell as administrator."
                )
            return rc

        # No arguments: run simple interactive menu.
        configure_style(use_color)
        while True:
            clear_screen()
            # Colored ASCII logo
            print_formatted_text(
                HTML(
                    f"""
<logo-main> 8b      db      d8 8b,dPPYba, 8b,dPPYba,</logo-main>    <logo-meta>Version: {VERSION}</logo-meta>
<logo-main> `8b    d88b    d8' 88P'   "Y8 88P'    "8a</logo-main>   <logo-meta>Github: {GITHUB}</logo-meta>
<logo-main>  `8b  d8'`8b  d8'  88         88       d8</logo-main>
<logo-main>   `8bd8'  `8bd8'   88         88b,   ,a8"</logo-main>
<logo-main>     YP      YP     88         88`YbbdP"'</logo-main>
<logo-main>                               88</logo-main>
<logo-main>                               88</logo-main>
"""
                ),
                style=style,
            )

            print_formatted_text(
                HTML("  <menu-number>1)</menu-number> <menu-text>List users</menu-text>"),
                style=style,
            )
            print_formatted_text(
                HTML("  <menu-number>2)</menu-number> <menu-text>Show user</menu-text>"),
                style=style,
            )
            print_formatted_text(
                HTML("  <menu-number>3)</menu-number> <menu-text>Create user</menu-text>"),
                style=style,
            )
            print_formatted_text(
                HTML("  <menu-number>4)</menu-number> <menu-text>Delete user</menu-text>"),
                style=style,
            )
            print_formatted_text(
                HTML("  <menu-number>5)</menu-number> <menu-text>Enable / disable user</menu-text>"),
                style=style,
            )
            print_formatted_text(
                HTML("  <menu-number>6)</menu-number> <menu-text>Change user password</menu-text>"),
                style=style,
            )
            print_formatted_text(
                HTML("  <menu-number>7)</menu-number> <menu-text>List local groups</menu-text>"),
                style=style,
            )
            print_formatted_text(
                HTML(
                    "  <menu-warn>8)</menu-warn> <menu-warn>Schedule Utilman.exe restore (after reboot)</menu-warn>"
                ),
                style=style,
            )
            print_formatted_text(
                HTML(
                    "  <menu-warn>9)</menu-warn> <menu-warn>Install Utilman.exe hook (replace with wrpbypass)</menu-warn>"
                ),
                style=style,
            )
            print_formatted_text(
                HTML(
                    "  <menu-warn>10)</menu-warn> <menu-warn>Restore Utilman.exe now (no reboot, if possible)</menu-warn>"
                ),
                style=style,
            )
            print_formatted_text(
                HTML("  <menu-number>11)</menu-number> <menu-text>Run custom program / command</menu-text>"),
                style=style,
            )
            print_formatted_text(
                HTML("  <menu-number>12)</menu-number> <menu-text>Show system info</menu-text>"),
                style=style,
            )
            print_formatted_text(
                HTML("  <menu-number>0)</menu-number> <menu-text>Exit</menu-text>"),
                style=style,
            )

            choice = ask("\nwrpbypass")

            try:
                if choice == "1":
                    ns = argparse.Namespace(domain=False)
                    cmd_user_list(ns)
                elif choice == "2":
                    name = ask("Username")
                    if name:
                        ns = argparse.Namespace(username=name, domain=False)
                        cmd_user_show(ns)
                elif choice == "3":
                    name = ask("New username")
                    if not name:
                        continue
                    password = ask("Password")
                    fullname = ask("Full name (optional, Enter to skip)")
                    active_raw = ask(
                        "Enable account immediately? [yes/no] (Enter=yes)"
                    ).strip().lower()
                    if active_raw not in ("yes", "no", ""):
                        active_raw = "yes"
                    ns = argparse.Namespace(
                        username=name,
                        password=password,
                        fullname=fullname or None,
                        active=None if active_raw == "" else active_raw == "yes",
                    )
                    cmd_user_add(ns)
                elif choice == "4":
                    name = ask("Username to delete")
                    if name:
                        confirm = ask(f"Delete user '{name}'? [yes/no]")
                        if confirm.strip().lower() == "yes":
                            ns = argparse.Namespace(username=name)
                            cmd_user_delete(ns)
                            log_action(f"Deleted user '{name}'")
                elif choice == "5":
                    name = ask("Username")
                    if not name:
                        continue
                    mode = ask("Enter 'on' to enable or 'off' to disable")
                    ns = argparse.Namespace(username=name)
                    if mode.lower().startswith("on"):
                        cmd_user_enable(ns)
                        log_action(f"Enabled user '{name}'")
                    elif mode.lower().startswith("off"):
                        cmd_user_disable(ns)
                        log_action(f"Disabled user '{name}'")
                    else:
                        warn("Invalid mode, use 'on' or 'off'.")
                elif choice == "6":
                    name = ask("Username")
                    if not name:
                        continue
                    password = ask("New password")
                    ns = argparse.Namespace(username=name, password=password)
                    cmd_user_set_password(ns)
                    log_action(f"Changed password for user '{name}'")
                elif choice == "7":
                    ns = argparse.Namespace()
                    cmd_group_list(ns)
                elif choice == "8":
                    confirm = ask(
                        "Schedule Utilman.exe restore on next reboot? [yes/no]"
                    )
                    if confirm.strip().lower() == "yes":
                        schedule_restore_utilman()
                        log_action("Scheduled Utilman.exe restore on reboot")
                elif choice == "9":
                    confirm = ask(
                        "Install Utilman.exe hook (replace with wrpbypass)? [yes/no]"
                    )
                    if confirm.strip().lower() == "yes":
                        install_utilman_hook()
                        log_action("Installed Utilman.exe hook")
                elif choice == "10":
                    confirm = ask(
                        "Try to restore Utilman.exe immediately (no reboot)? [yes/no]"
                    )
                    if confirm.strip().lower() == "yes":
                        restore_utilman_now()
                        log_action("Tried immediate Utilman.exe restore")
                elif choice == "11":
                    print_formatted_text(
                        HTML(
                            "<info>Presets:</info>\n"
                            "  1) cmd.exe\n"
                            "  2) powershell.exe\n"
                            "  3) explorer.exe\n"
                            "  4) mmc.exe\n"
                        ),
                        style=style,
                    )
                    preset = ask("Preset number (Enter=custom)")
                    if preset == "1":
                        cmdline = "cmd.exe"
                    elif preset == "2":
                        cmdline = "powershell.exe"
                    elif preset == "3":
                        cmdline = "explorer.exe"
                    elif preset == "4":
                        cmdline = "mmc.exe"
                    else:
                        cmdline = ask(
                            "Enter full command or path to program (e.g. cmd.exe or C:\\Windows\\System32\\cmd.exe)"
                        )
                    if not cmdline:
                        continue
                    start_dir = ask(
                        "Start directory (Enter = current working directory)"
                    ).strip()
                    cwd = start_dir or None
                    try:
                        completed = subprocess.run(cmdline, shell=True, cwd=cwd)
                        info(f"Program exited with code {completed.returncode}.")
                        log_action(
                            f"Ran program '{cmdline}' (cwd={cwd or 'current'}) exit={completed.returncode}"
                        )
                    except Exception as e:
                        error(f"Failed to run program: {e}")
                        log_action(f"Failed to run program '{cmdline}': {e}")
                elif choice == "12":
                    # Show basic system info and optional Administrators membership
                    comp_name = os.environ.get("COMPUTERNAME", "")
                    user_name = os.environ.get("USERNAME") or getpass.getuser()
                    domain = os.environ.get("USERDOMAIN", "")
                    win_ver = platform.platform()
                    print_formatted_text(
                        HTML(
                            f"<info>Computer:</info> {comp_name or 'unknown'}\n"
                            f"<info>User:</info> {user_name}\n"
                            f"<info>Domain/Workgroup:</info> {domain or 'unknown'}\n"
                            f"<info>Windows:</info> {win_ver}"
                        ),
                        style=style,
                    )
                    check_user = ask(
                        "Username to check in Administrators (Enter to skip)"
                    ).strip()
                    if check_user:
                        proc = capture_output(
                            ["net", "localgroup", "Administrators"]
                        )
                        is_admin = False
                        if proc and proc.stdout:
                            for line in proc.stdout.splitlines():
                                if check_user.lower() in line.lower().split():
                                    is_admin = True
                                    break
                        if is_admin:
                            ok(f"User '{check_user}' IS in Administrators group.")
                        else:
                            warn(
                                f"User '{check_user}' is NOT in Administrators group."
                            )
                    log_action("Viewed system info screen")
                elif choice == "0":
                    ok("Exit.")
                    return 0
                else:
                    warn("Unknown menu item.")
            except KeyboardInterrupt:
                ok("\nExit by Ctrl+C.")
                return 0

            # Small pause so the user can read command output before the screen is cleared.
            try:
                pause("")
            except KeyboardInterrupt:
                ok("\nExit by Ctrl+C.")
                return 0
    except KeyboardInterrupt:
        ok("\nExit by Ctrl+C.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

