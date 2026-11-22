# Network Focus installer for Windows. Installs or updates everything, then opens the CEO dashboard.
#   Double-click "Install Network Focus.cmd", or paste into PowerShell:
#   irm https://raw.githubusercontent.com/jasper-osita/network-focus-maven/main/install.ps1 | iex
#   Uninstall (keeps your briefs):  powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall
param([switch]$Uninstall)

$Repo = 'jasper-osita/network-focus-maven'
$PluginId = 'network-focus@network-focus'
$Marketplace = 'network-focus'
$TestMode = [bool]$env:NF_INSTALL_TEST

$AppDir = Join-Path $env:LOCALAPPDATA 'Network Focus'
New-Item -ItemType Directory -Force -Path $AppDir | Out-Null
$Log = Join-Path $AppDir 'install.log'
try { Start-Transcript -Path $Log -Append | Out-Null } catch {}

function Step($text) { Write-Host ''; Write-Host $text -ForegroundColor White }
function Ok($text) { Write-Host "  [OK] $text" -ForegroundColor Green }
function Fail($text, $fix) {
  Write-Host ''
  Write-Host "  [X] $text" -ForegroundColor Red
  if ($fix) { Write-Host "    What to do: $fix" }
  Write-Host "    (Details are saved in $Log)"
  try { Stop-Transcript | Out-Null } catch {}
  exit 1
}
function Has($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
  # pick up tools installed a moment ago without reopening the window
  $env:Path = "$env:USERPROFILE\.local\bin;" + $env:Path + ';' +
    [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
}
function Folder($name) {
  if ($TestMode) {
    if ($name -eq 'Startup') { return Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup' }
    return Join-Path $env:USERPROFILE $name
  }
  if ($name -eq 'Documents') { return [Environment]::GetFolderPath('MyDocuments') }
  return [Environment]::GetFolderPath($name)
}
function Stop-Page {
  $cfgFile = Join-Path $AppDir 'config.json'
  if (-not (Test-Path $cfgFile)) { return }
  try {
    $cfg = Get-Content $cfgFile -Raw | ConvertFrom-Json
    $origin = "http://127.0.0.1:$($cfg.port)"
    Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$origin/api/quit" -Body '{}' -ContentType 'application/json' `
      -Headers @{ Origin = $origin; Cookie = "nf_token=$($cfg.token)" } -TimeoutSec 3 | Out-Null
  } catch {}
}

$env:Path = "$env:USERPROFILE\.local\bin;" + $env:Path

# ---------------------------------------------------------------- uninstall
if ($Uninstall) {
  Step 'Removing Network Focus (your briefs in Documents > Network Focus are kept)...'
  Stop-Page
  Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path (Folder 'Startup') 'Network Focus.vbs')
  Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path (Folder 'Desktop') 'Network Focus.url')
  if (Has 'claude') { claude plugin uninstall $PluginId 2>&1 | Out-Null }
  try { Stop-Transcript | Out-Null } catch {}
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $AppDir
  Write-Host '  [OK] Removed the page, the Desktop shortcut and the plugin.' -ForegroundColor Green
  Write-Host '  [OK] Your folder Documents > Network Focus is still there.' -ForegroundColor Green
  exit 0
}

Write-Host ''
Write-Host "Installing Network Focus. This takes a few minutes; you'll only need to sign in to Claude."

# ---------------------------------------------------------------- 1. helpers
Step '1/5  Checking the helper programs...'
if (Has 'uv') { Ok 'uv is already installed.' } else {
  if ($TestMode) { Fail 'uv is missing.' 'Install uv for the test run.' }
  Write-Host '  Installing uv...'
  powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
  Refresh-Path
  if (-not (Has 'uv')) { Fail "uv didn't install." 'Check the internet connection and run the installer again.' }
  Ok 'Installed uv.'
}
if (Has 'git') { Ok 'Git is already installed.' } else {
  # Claude Code on Windows uses Git for Windows for its command shell
  Write-Host '  Installing Git for Windows...'
  if (Has 'winget') {
    winget install --id Git.Git -e --silent --accept-package-agreements --accept-source-agreements | Out-Null
    Refresh-Path
  }
  if (-not (Has 'git')) { Fail "Git for Windows isn't installed." 'Install it from https://git-scm.com/download/win, then run the installer again.' }
  Ok 'Installed Git for Windows.'
}
if (Has 'claude') { Ok 'Claude Code is already installed.' } else {
  if ($TestMode) { Fail 'claude is missing.' 'Provide the stand-in for the test run.' }
  Write-Host '  Installing Claude Code...'
  powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://claude.ai/install.ps1 | iex'
  Refresh-Path
  if (-not (Has 'claude')) { Fail "Claude Code didn't install." 'Check the internet connection and run the installer again.' }
  Ok 'Installed Claude Code.'
}

# ---------------------------------------------------------------- 2. sign in
Step "2/5  Checking you're signed in to Claude..."
function Signed-In { ((claude auth status --json 2>$null) | Out-String) -match '"loggedIn":\s*true' }
if (Signed-In) { Ok 'Already signed in.' } else {
  Write-Host '  Your browser will open. Sign in to Claude there, then come back to this window.'
  claude auth login
  if (-not (Signed-In)) { Fail "You're not signed in to Claude yet." 'Run the installer again and finish signing in when the browser opens.' }
  Ok 'Signed in.'
}

# ---------------------------------------------------------------- 3. plugin
Step '3/5  Installing the Network Focus plugin...'
$markets = (claude plugin marketplace list --json 2>$null) | Out-String
if ($markets -match ('"' + $Marketplace + '"')) {
  claude plugin marketplace update $Marketplace | Out-Null
} else {
  claude plugin marketplace add $Repo | Out-Null
}
if ($LASTEXITCODE -ne 0) { Fail "Couldn't reach Network Focus on GitHub." 'Check the internet connection and run the installer again.' }
$plugins = (claude plugin list --json 2>$null) | Out-String
if ($plugins -match [regex]::Escape('"' + $PluginId + '"')) {
  claude plugin update $PluginId | Out-Null
  if ($LASTEXITCODE -ne 0) { Fail "Couldn't update the plugin." 'Run the installer again.' }
  Ok 'Updated the plugin.'
} else {
  claude plugin install $PluginId | Out-Null
  if ($LASTEXITCODE -ne 0) { Fail "Couldn't install the plugin." 'Run the installer again.' }
  Ok 'Installed the plugin.'
}
$PluginDir = ((claude plugin list --json 2>$null) | Out-String | ConvertFrom-Json) |
  Where-Object { $_.id -eq $PluginId } | Select-Object -First 1 -ExpandProperty installPath
if (-not $PluginDir -or -not (Test-Path (Join-Path $PluginDir 'app\install_app.py'))) {
  Fail "Couldn't find the installed plugin." 'Run the installer again.'
}

# ---------------------------------------------------------------- 4. page
Step '4/5  Setting up the Network Focus page and your folder...'
$extra = @('--nf-home', (Join-Path (Folder 'Documents') 'Network Focus'))
if ($TestMode) { $extra += '--no-launch' } else { Stop-Page }
$output = (uv run --quiet (Join-Path $PluginDir 'app\install_app.py') @extra) | Out-String
if ($LASTEXITCODE -ne 0) { Fail "Couldn't set up the page." 'Run the installer again; if it repeats, send the log to whoever set this up.' }
$result = ($output.Trim() -split "`n")[-1] | ConvertFrom-Json
foreach ($w in $result.warnings) { Write-Host "  ! $w" -ForegroundColor Yellow }
Ok 'Folder: Documents > Network Focus'
Ok 'Desktop shortcut: Network Focus'

# ---------------------------------------------------------------- 5. open
Step '5/5  Opening the dashboard...'
if (-not $TestMode -and $result.url) { Start-Process $result.url }
Ok 'Done. Network Focus is installed.'
Write-Host ''
Write-Host "Every Monday: double-click Network Focus on the Desktop, drop in this week's spreadsheet"
Write-Host "on the 'Make the brief' tab, and click Generate. The dashboard shows the CEO's #1 for the week."
try { Stop-Transcript | Out-Null } catch {}
exit 0
