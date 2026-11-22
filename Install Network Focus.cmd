@echo off
rem Double-click to install or update Network Focus on this PC.
rem Uses install.ps1 next to this file if there is one, otherwise the latest from GitHub.
setlocal
cd /d "%~dp0"
if exist "%~dp0install.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((irm 'https://raw.githubusercontent.com/jasper-osita/network-focus-maven/main/install.ps1'))) %*"
)
echo.
pause
