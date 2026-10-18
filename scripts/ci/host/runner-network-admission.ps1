# Admit or withdraw an overflow runner by its measured egress (#2279).
#
# Windows twin of runner-network-admission.sh, for the en-home WSL runner,
# whose traffic leaves through the Windows host. It downloads the same fixed
# 10 MiB range with the same thresholds and toggles the runner's admission
# label through the Runner API: two consecutive fast samples admit it, one
# slow or failed sample withdraws it. Requires an authenticated `gh` with
# admin access to the repository, so it runs as the logged-in user.
#
# Install as a scheduled task every 10 minutes. Point it at the stable App
# Execution Alias, %LOCALAPPDATA%\Microsoft\WindowsApps\pwsh.exe, never the
# versioned C:\Program Files\WindowsApps\Microsoft.PowerShell_<version>_...
# path: a Store update removes that directory and the task then fails with
# 0x80070002 on every run (observed 2026-10-17).
param(
  [string]$Repository = "endaye/lmdj",
  [int]$RunnerId = 24,
  [string]$Label = "ci-web-overflow",
  [string]$StateDirectory = (Join-Path $env:ProgramData "lmdj-ci")
)
$ErrorActionPreference = "Stop"
$AdmitBytesPerSecond = 2097152
$RevokeBytesPerSecond = 512000
$AdmitStreak = 2
$ProbeUrl = "https://github.com/actions/runner/releases/download/v2.338.0/actions-runner-linux-x64-2.338.0.tar.gz"
New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
$stateFile = Join-Path $StateDirectory "admission-state.json"
$logFile = Join-Path $StateDirectory "admission.log"
function Write-AdmissionLog([string]$message) {
  Add-Content -Path $logFile -Value ("{0:u} {1}" -f (Get-Date).ToUniversalTime(), $message)
}
$state = @{ goodStreak = 0 }
if (Test-Path $stateFile) { try { $state = Get-Content $stateFile -Raw | ConvertFrom-Json -AsHashtable } catch { } }

$speed = 0.0
$out = & curl.exe -sS -L -o NUL -r 0-10485759 --max-time 30 -w "%{speed_download} %{size_download} %{http_code}" $ProbeUrl 2>&1
if ($LASTEXITCODE -eq 0 -and "$out" -match '^([\d.]+) (\d+) (\d+)$' -and [int]$Matches[3] -lt 400 -and [int64]$Matches[2] -gt 1048576) {
  $speed = [double]$Matches[1]
}
try {
  $labels = (& gh api "repos/$Repository/actions/runners/$RunnerId" --jq '[.labels[].name]|join(",")') -split ","
  if ($LASTEXITCODE -ne 0) { throw "gh exited $LASTEXITCODE" }
} catch {
  Write-AdmissionLog "gh-error $_"
  exit 0
}
$admitted = $labels -contains $Label
if ($speed -ge $AdmitBytesPerSecond) { $state.goodStreak = [int]$state.goodStreak + 1 } else { $state.goodStreak = 0 }
$action = "keep"
if ($admitted -and $speed -lt $RevokeBytesPerSecond) {
  & gh api -X DELETE "repos/$Repository/actions/runners/$RunnerId/labels/$Label" --silent; $action = "revoke"
} elseif (-not $admitted -and $state.goodStreak -ge $AdmitStreak) {
  & gh api -X POST "repos/$Repository/actions/runners/$RunnerId/labels" -f "labels[]=$Label" --silent; $action = "admit"
}
$state | ConvertTo-Json | Set-Content -Path $stateFile
Write-AdmissionLog ("speed={0:N0}B/s curl='{1}' admitted={2} streak={3} action={4}" -f $speed, "$out", $admitted, $state.goodStreak, $action)
