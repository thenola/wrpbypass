# wrpbypass

Windows recovery helper for managing local users and temporarily replacing `Utilman.exe` from both Windows and Linux (Debian/Ubuntu Live).

## Overview

`wrpbypass` is a small toolkit designed for **offline administration** of Windows machines:

- Manage local users and groups from a friendly TUI/CLI.
- Temporarily replace `C:\Windows\System32\Utilman.exe` with `wrpbypass.exe` so that the **Ease of Access** button on the logon screen starts this tool.
- Safely restore the original `Utilman.exe`, either immediately or on the next reboot.
- Perform the same replacement/restore operations from **Debian/Ubuntu Live** using `wrpbypass_deb.py`.

> **Important**
> This tool is intended for legitimate administration and recovery on systems you have permission to manage. Misuse may violate local law or policy.

## Components

- `wrpbypass.py` – main Windows tool
  - CLI with `argparse` for scripting.
  - Interactive text menu (when run without arguments).
  - Colored output using `prompt_toolkit` (falls back to plain `input()` if unavailable).
  - Can manage users, groups, and the `Utilman.exe` hook.

- `wrpbypass_deb.py` – Linux helper
  - Must be run as `root` on Debian/Ubuntu (e.g., from a Live USB).
  - Mounts a Windows partition and replaces/restores `Utilman.exe` on that offline installation.
  - Supports a `--dry-run` mode (simulation only).

- `build_windows.bat` – build self‑contained Windows executable (`Utilman.exe`) via PyInstaller.
- `build_debian.bat` – prepare a **Debian helper bundle** (`wrpbypass_debian.zip`) on Windows.
- `build_debian.sh` – build a self‑contained Linux executable from `wrpbypass_deb.py` on Debian/Ubuntu (`dist_debian/wrpbypass_deb`).
- `VERSION` – current version string.
- `requirements.txt` – Python dependencies for Windows build (`pyfiglet`, `prompt_toolkit`).

## Features

### Windows interactive menu (no arguments)

When you run `wrpbypass.exe` (or `python wrpbypass.py`) **without arguments**, you get a simple colored menu:

- `1` – List users
- `2` – Show user details
- `3` – Create user
- `4` – Delete user (with confirmation)
- `5` – Enable / disable user
- `6` – Change user password
- `7` – List local groups
- `8` – Schedule `Utilman.exe` restore on next reboot
- `9` – Install `Utilman.exe` hook (replace with `wrpbypass`)
- `10` – Try to restore `Utilman.exe` immediately (no reboot, if possible)
- `11` – Run custom program / command (with presets for `cmd.exe`, `powershell.exe`, etc.)
- `12` – Show system info and check if a user is in the `Administrators` group
- `0` – Exit

Additional behaviour:

- Screen is cleared between menu iterations (`cls` on Windows).
- If `prompt_toolkit` cannot be used (for example when started as `Utilman.exe`), all input falls back to plain `input()` automatically.
- `Ctrl+C` anywhere results in a clean exit with a short message, without a Python traceback.
- Actions are logged to `wrpbypass.log` in the working directory.

When compiled as `Utilman.exe` and started via the Ease of Access button, Windows may pass the argument `/debug`. `wrpbypass` detects this and ignores the argument, going straight into the interactive menu.

### Windows CLI (arguments)

With arguments, `wrpbypass` behaves as a classic command‑line tool. Some examples (run in an elevated Command Prompt / PowerShell):

```bash
# list local users
wrpbypass.exe user list

# show a specific user
wrpbypass.exe user show alice

# create user
wrpbypass.exe user add alice P@ssw0rd --fullname "Alice Example" --active yes

# delete user
wrpbypass.exe user delete alice

# enable / disable
wrpbypass.exe user enable alice
wrpbypass.exe user disable alice

# set password
wrpbypass.exe user set-password alice NewP@ssw0rd

# list local groups
wrpbypass.exe group list

# view group
wrpbypass.exe group show Administrators

# install Utilman hook
wrpbypass.exe utilman install

# schedule restore on next reboot
wrpbypass.exe utilman schedule-restore

# try immediate restore
wrpbypass.exe utilman restore-now
```

> The underlying implementation uses `net user` and `net localgroup` under the hood, so administrator privileges are required for most operations.

### Linux / Debian (offline Windows)

On Debian/Ubuntu Live:

- `wrpbypass_deb.py`:
  - Takes a Windows partition device (e.g. `/dev/sda1`), mounts it, and operates on `Windows/System32/Utilman.exe` inside that mounted root.
  - Two modes:
    - `install` – backup original `Utilman.exe` to `Utilman.exe.tmp`, copy `wrpbypass.exe` to `wrpbypass.exe`, and replace `Utilman.exe` with it.
    - `restore` – revert the backup and remove any leftover `wrpbypass.exe`.
  - Safe checks:
    - Verifies that `Windows/System32` exists on the selected partition.
    - Verifies the presence of `Utilman.exe` and `Utilman.exe.tmp` as needed.
  - `--dry-run` option shows everything that would be done, without touching any files.

- `pydeb.sh` is a helper wrapper script that:
  - Ensures `wrpbypass_deb.py` is executable.
  - Shows `lsblk` output to help you pick the right Windows partition.
  - Asks whether to **install hook** or **restore**.
  - Optionally auto‑detects `wrpbypass.exe` built on Windows (e.g., from a USB drive) and passes its path to `wrpbypass_deb.py`.

## Building on Windows

### 1. Clone / copy the project

Make sure you have Python 3.10+ and `pip` installed.

```bash
cd C:\Users\Local\Desktop\wrpbypass\wrpbypass
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
```

### 2. Build Windows `Utilman.exe`

Use the provided batch file:

```bash
build_windows.bat
```

This runs:

```bat
pyinstaller -F wrpbypass.py --name Utilman --distpath dist
```

The resulting file will be:

- `dist\Utilman.exe`

You can rename it if desired (for example to `wrpbypass.exe`) before copying to `C:\Windows\System32`.

> **If you see `PermissionError: [WinError 5] Access is denied: 'C:\\Users\\...\\dist\\Utilman.exe' during build**
>
> This usually means `Utilman.exe` from the last build is still running (for example, you launched it for testing and did not close it).  
> Before rebuilding:
> - Close all consoles / windows that were started via this `Utilman.exe`.  
> - In Task Manager, find and **end the `Utilman.exe` process** (if it is still present).  
> - Then re‑run `build_windows.bat`.

### 3. Build Debian helper ZIP from Windows

To prepare files for Debian/Ubuntu Live, from Windows:

```bash
build_debian.bat
```

This will create a helper archive:

- `dist\wrpbypass_debian.zip` – ready to copy to a USB stick.

## Building on Debian/Ubuntu

### Option A: Use Python script directly

1. Copy `wrpbypass_debian.zip` from Windows to your Debian/Ubuntu Live system.
2. Extract:

```bash
unzip wrpbypass_debian.zip
cd wrpbypass
chmod +x wrpbypass_deb.py
```

3. Run interactive helper:

```bash
sudo python3 wrpbypass_deb.py
```

`wrpbypass_deb.py` with **no arguments** now shows an interactive menu (device selection, mode `install` / `restore`, path to `Utilman.exe`), полностью заменяя старый `pydeb.sh`.

### Option B: Build a standalone Linux binary

In Debian/Ubuntu (after extracting the project):

```bash
python3 -m pip install pyinstaller
chmod +x build_debian.sh
./build_debian.sh
```

The resulting binary will be:

- `dist_debian/wrpbypass_deb`

You can then run it directly:

```bash
sudo ./dist_debian/wrpbypass_deb --device /dev/sda1 --mountpoint /mnt/win --mode install --wrpbypass-exe /path/to/wrpbypass.exe
```

## Typical Scenarios

### 1. Prepare hook on an offline Windows installation (from Linux)

1. Boot into Debian/Ubuntu Live.
2. Copy `wrpbypass.exe` and `wrpbypass_deb.py` (or unpack `wrpbypass_debian.zip`).
3. Run:

```bash
sudo python3 wrpbypass_deb.py
```

4. In the interactive menu choose **Install hook**, select the correct Windows partition and path to `Utilman.exe` (or your `wrpbypass.exe` build).
5. Reboot into Windows; on the logon screen press the **Ease of Access** button to start `wrpbypass` instead of the usual accessibility tools.

### 2. Restore the original `Utilman.exe` from Linux

Same as above, but in the interactive menu choose **Restore original Utilman.exe**.

### 3. Restore `Utilman.exe` from Windows

From inside `wrpbypass` interactive menu on Windows:

- Use `8` to **schedule a restore on next reboot**.
- Or `10` to **attempt immediate restore** (if the file is not locked or in use).

From CLI:

```bash
wrpbypass.exe utilman schedule-restore
wrpbypass.exe utilman restore-now
```

## Safety Notes

- Always ensure you have **physical access and authorization** to the machine.
- When operating from Linux, double‑check you selected the correct Windows partition (`lsblk` output helps).
- `wrpbypass_deb.py` and the Windows restore functions attempt to only touch:
  - `Windows\System32\Utilman.exe`
  - `Windows\System32\Utilman.exe.tmp`
  - `Windows\System32\wrpbypass.exe` (optional helper)
- A backup of `Utilman.exe` is stored as `Utilman.exe.tmp` before replacement.

## Known Behaviours / Troubleshooting

- **`/debug` argument on Windows logon**
  - When `Utilman.exe` is started from the logon screen, Windows may pass `/debug`. The tool detects this and ignores it, entering the interactive menu.

- **`prompt_toolkit` or console issues**
  - In restricted environments (like the logon screen) advanced console libraries may fail.
  - `wrpbypass` catches such errors and falls back to plain `input()` for all prompts.

- **`pyfiglet` fonts in PyInstaller build**
  - The ASCII banner uses `pyfiglet`. In the packaged EXE, fonts may not be available.
  - The banner rendering is wrapped in `try/except` so that failure will not crash the program; at worst, you simply won’t see the ASCII logo.

## Configuration and Logging

### Config file (`config.yml`)

`wrpbypass` reads a very simple YAML‑like config file:

- Location (on Windows by default): `C:\ProgramData\wrpbypass\config.yml`  
  - You can override the base directory by setting the `WRP_DIR` environment variable.

On first start, a default `config.yml` is created:

```yaml
# wrpbypass configuration
# color: true|false (default: true)
color: true
# log_enabled: true|false (default: true)
log_enabled: true
# log_commands: true|false (default: true) – log underlying net/command calls
log_commands: true
```

Options:

- `color` – enables/disables colored output (menu + messages).
  - Can also be forced off with environment variable `WRP_NOCOLOR=1`.
- `log_enabled` – master switch for logging:
  - `true` – all events are written to the log.
  - `false` – logging is completely disabled.
- `log_commands` – when `true`, internal calls that you choose to log (e.g. `net user` / `net localgroup`) are also written to the log.  
  (The code uses this flag to decide, какие команды писать подробнее.)

### Log file (`wrpbypass.log`)

By default on Windows the log is stored in:

- `C:\ProgramData\wrpbypass\wrpbypass.log`

You can change the base directory by setting `WRP_DIR` before starting `wrpbypass`; in that case both `config.yml` and `wrpbypass.log` will be placed under that folder.

Format:

- At the beginning of each run `wrpbypass` writes a **session header**:
  - Start time, tool version, mode (`cli` or `interactive`), computer name, user, domain, executable path, data directory, `WRP_DIR`/`WRP_NOCOLOR` values, Windows version.
- Each subsequent line is an event:
  - `[{timestamp}][{mode}] {action}`
  - Where `{mode}` is `cli` or `interactive`.

This extended log is intended to make it easier to audit what exactly было сделано во время сессии восстановления.

