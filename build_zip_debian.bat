@echo off
setlocal

REM Build helper bundle for Debian/Ubuntu Live from Windows.
REM Creates dist\debian\ with Linux helper scripts and packs them to ZIP.

set "SCRIPT_DIR=%~dp0"
set "DIST_DIR=%SCRIPT_DIR%dist\debian"

if not exist "%SCRIPT_DIR%dist" (
    mkdir "%SCRIPT_DIR%dist"
)

if not exist "%DIST_DIR%" (
    mkdir "%DIST_DIR%"
)

copy /Y "%SCRIPT_DIR%wrpbypass_deb.py" "%DIST_DIR%\" >nul
copy /Y "%SCRIPT_DIR%pydeb.sh" "%DIST_DIR%\" >nul
if exist "%SCRIPT_DIR%chmod.txt" (
    copy /Y "%SCRIPT_DIR%chmod.txt" "%DIST_DIR%\" >nul
)

echo [*] Debian helper files copied to dist\debian

REM Pack to ZIP so it is easy to move to a USB stick
powershell -NoLogo -NoProfile -Command ^
 "Compress-Archive -Path '%DIST_DIR%\*' -DestinationPath '%SCRIPT_DIR%dist\wrpbypass_debian.zip' -Force" >nul

echo [*] Created archive: dist\wrpbypass_debian.zip
echo [*] On Debian/Ubuntu Live: unzip and run ./pydeb.sh

endlocal

