# Admit or withdraw the en-home overflow runner by its host conditions (#2279).
#
# Windows twin of runner-network-admission.sh, for the en-home WSL runner,
# whose traffic leaves through this Windows host. The runner may take the Web
# lanes only while all of these hold (owner policy, 2026-10-18):
#   - the owner has been idle for at least 15 minutes;
#   - no Windows Update or servicing reboot is pending;
#   - at least 30 GB free on the drive holding the runner's WSL distribution;
#   - the CI egress is fast: the same 10 MiB GitHub range as the bash twin,
#     every 10 minutes, admitted after two consecutive samples of at least
#     2 MiB/s and withdrawn after one under 500 KiB/s or a failed download.
# Any failing condition withdraws the label; a job already running continues.
# An unreadable Runner API changes nothing, and a failed label write is logged
# as such and retried on the next run. Requires an authenticated `gh` with
# admin access to the repository, so it runs as the logged-in user.
#
# Install as a scheduled task every minute, in the owner's interactive session
# (idle time is per session). Point it at the stable App Execution Alias,
# %LOCALAPPDATA%\Microsoft\WindowsApps\pwsh.exe, never the versioned
# C:\Program Files\WindowsApps\Microsoft.PowerShell_<version>_... path: a Store
# update removes that directory and the task then fails with 0x80070002 on
# every run (observed 2026-10-17).
param(
  [string]$Repository = "endaye/lmdj",
  [int]$RunnerId = 24,
  [string]$Label = "ci-web-overflow",
  [string]$Distribution = "LMDJ-Runner-Ubuntu",
  [string]$StateDirectory = (Join-Path $env:ProgramData "lmdj-ci")
)
$ErrorActionPreference = "Stop"
$AdmitBytesPerSecond = 2097152
$RevokeBytesPerSecond = 512000
$AdmitStreak = 2
$ProbeIntervalSeconds = 600
$IdleMinSeconds = 900
$DiskMinGB = 30
$ProbeUrl = "https://github.com/actions/runner/releases/download/v2.338.0/actions-runner-linux-x64-2.338.0.tar.gz"
New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
$stateFile = Join-Path $StateDirectory "admission-state.json"
$logFile = Join-Path $StateDirectory "admission.log"
function Write-AdmissionLog([string]$message) {
  Add-Content -Path $logFile -Value ("{0:u} {1}" -f (Get-Date).ToUniversalTime(), $message)
}
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$state = @{ goodStreak = 0; network = "unknown"; probedAt = 0 }
if (Test-Path $stateFile) {
  try { $loaded = Get-Content $stateFile -Raw | ConvertFrom-Json -AsHashtable; foreach ($k in $loaded.Keys) { $state[$k] = $loaded[$k] } } catch { }
}

if ($now - [int64]$state.probedAt -ge $ProbeIntervalSeconds) {
  $speed = 0.0
  $out = & curl.exe -sS -L -o NUL -r 0-10485759 --max-time 30 -w "%{speed_download} %{size_download} %{http_code}" $ProbeUrl 2>&1
  if ($LASTEXITCODE -eq 0 -and "$out" -match '^([\d.]+) (\d+) (\d+)$' -and [int]$Matches[3] -lt 400 -and [int64]$Matches[2] -gt 1048576) {
    $speed = [double]$Matches[1]
  }
  if ($speed -ge $AdmitBytesPerSecond) { $state.goodStreak = [int]$state.goodStreak + 1 } else { $state.goodStreak = 0 }
  if ($speed -lt $RevokeBytesPerSecond) { $state.network = "slow" }
  elseif ($state.goodStreak -ge $AdmitStreak) { $state.network = "fast" }
  $state.probedAt = $now
  Write-AdmissionLog ("probe speed={0:N0}B/s curl='{1}' streak={2} network={3}" -f $speed, "$out", $state.goodStreak, $state.network)
}

$blockers = @()
if (-not ("LmdjIdle" -as [type])) {
  Add-Type @"
using System; using System.Runtime.InteropServices;
public static class LmdjIdle {
  [StructLayout(LayoutKind.Sequential)] struct LASTINPUTINFO { public uint cbSize; public uint dwTime; }
  [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LASTINPUTINFO info);
  public static uint Seconds() {
    var info = new LASTINPUTINFO(); info.cbSize = (uint)Marshal.SizeOf(info);
    if (!GetLastInputInfo(ref info)) return 0;
    return ((uint)Environment.TickCount - info.dwTime) / 1000;
  }
}
"@
}
if ([LmdjIdle]::Seconds() -lt $IdleMinSeconds) { $blockers += "user-active" }
$rebootKeys = @(
  "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired",
  "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending")
if ($rebootKeys | Where-Object { Test-Path $_ }) { $blockers += "reboot-pending" }
$basePath = Get-ChildItem "HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss" -ErrorAction SilentlyContinue |
  ForEach-Object { Get-ItemProperty $_.PSPath } | Where-Object { $_.DistributionName -eq $Distribution } |
  Select-Object -First 1 -ExpandProperty BasePath
$drive = if ($basePath) { ($basePath -replace '^\\\\\?\\', '').Substring(0, 1) } else { $env:SystemDrive.Substring(0, 1) }
$freeGB = [math]::Floor((Get-PSDrive -Name $drive).Free / 1GB)
if ($freeGB -lt $DiskMinGB) { $blockers += "disk<${DiskMinGB}GB" }
if ($state.network -ne "fast") { $blockers += "network-$($state.network)" }
$state | ConvertTo-Json | Set-Content -Path $stateFile

try {
  $labels = (& gh api "repos/$Repository/actions/runners/$RunnerId" --jq '[.labels[].name]|join(",")') -split ","
  if ($LASTEXITCODE -ne 0) { throw "gh exited $LASTEXITCODE" }
} catch {
  Write-AdmissionLog "gh-error $_"
  exit 0
}
$admitted = $labels -contains $Label
# A native command's failure does not throw under "Stop", so each label write
# checks its exit code.
$action = "keep"
if ($admitted -and $blockers.Count -gt 0) {
  & gh api -X DELETE "repos/$Repository/actions/runners/$RunnerId/labels/$Label" --silent
  $action = if ($LASTEXITCODE -eq 0) { "revoke" } else { "revoke-failed" }
} elseif (-not $admitted -and $blockers.Count -eq 0) {
  & gh api -X POST "repos/$Repository/actions/runners/$RunnerId/labels" -f "labels[]=$Label" --silent
  $action = if ($LASTEXITCODE -eq 0) { "admit" } else { "admit-failed" }
}
# Log every change, and otherwise only when the blockers change.
$summary = "admitted=$admitted blockers=$(if ($blockers) { $blockers -join ' ' } else { 'none' }) action=$action"
$last = if (Test-Path $logFile) { (Get-Content $logFile -Tail 1) -replace '^\S+ \S+ ', '' } else { "" }
if ($action -ne "keep" -or $summary -ne $last) { Write-AdmissionLog $summary }
