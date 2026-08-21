param(
    [ValidateSet("Start", "Stop", "EmergencyStop", "Status")]
    [string]$Action = "Status",
    [ValidatePattern("^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")]
    [string]$LineageId = "early-game-development",
    [string]$InitialState = "",
    [ValidateSet("lmstudio-chat", "openai-responses", "replay")]
    [string]$Provider = "lmstudio-chat",
    [string]$Model = "",
    [string]$ReplayPath = "",
    [int]$MaxActions = 100,
    [switch]$NoVideo,
    [switch]$NoOperationsStart
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$SupervisorRoot = Join-Path $ProjectRoot "research\artifacts\segment-supervisor"
$LineageRoot = Join-Path $SupervisorRoot "lineages\$LineageId"
$ManifestPath = Join-Path $LineageRoot "manifest.json"
$StatePath = Join-Path $LineageRoot "state.json"
$LauncherDirectory = Join-Path $SupervisorRoot "launcher"
$ProcessPath = Join-Path $LauncherDirectory "$LineageId.json"
$LogDirectory = Join-Path $LauncherDirectory "logs"
$OperationsDirectory = Join-Path $ProjectRoot "research\artifacts\operations"
$OperationsControl = Join-Path $OperationsDirectory "control.json"
$OperationsUrl = "http://127.0.0.1:8766"

New-Item -ItemType Directory -Force -Path $LauncherDirectory, $LogDirectory | Out-Null

function Read-JsonFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    try {
        return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Test-Endpoint([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Get-TrackedSupervisor {
    $record = Read-JsonFile $ProcessPath
    if (-not $record -or -not $record.Id -or -not $record.StartedUtc) {
        return $null
    }
    $process = Get-Process -Id ([int]$record.Id) -ErrorAction SilentlyContinue
    if (-not $process) {
        return $null
    }
    try {
        $expected = [DateTimeOffset]::Parse([string]$record.StartedUtc).UtcDateTime
        $actual = $process.StartTime.ToUniversalTime()
        if ([Math]::Abs(($actual - $expected).TotalSeconds) -gt 1) {
            return $null
        }
    } catch {
        return $null
    }
    return $process
}

function Write-LocalControl([string]$ControlAction) {
    New-Item -ItemType Directory -Force -Path $OperationsDirectory | Out-Null
    $current = Read-JsonFile $OperationsControl
    $revision = if ($current -and $current.revision) { [int]$current.revision + 1 } else { 1 }
    $state = if ($ControlAction -eq "emergency_stop") { "emergency_stopped" } else { "running" }
    $stopAfterAction = $ControlAction -eq "stop_after_action"
    $temporary = Join-Path $OperationsDirectory ".control.$([Guid]::NewGuid().ToString('N')).tmp"
    @{
        schema = "operations_control_v1"
        revision = $revision
        state = $state
        stopAfterAction = $stopAfterAction
        updatedUtc = [DateTime]::UtcNow.ToString("o")
        lastCommandId = [Guid]::NewGuid().ToString("N")
    } | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding utf8
    [System.IO.File]::Move($temporary, $OperationsControl, $true)
}

function Send-Control([string]$ControlAction) {
    if (Test-Endpoint "$OperationsUrl/health") {
        $body = @{ action = $ControlAction; source = "supervisor_launcher" } | ConvertTo-Json
        Invoke-RestMethod -Uri "$OperationsUrl/control" -Method Post -ContentType "application/json" -Body $body | Out-Null
    } else {
        Write-LocalControl $ControlAction
    }
}

function Show-Status {
    $state = Read-JsonFile $StatePath
    $process = Get-TrackedSupervisor
    Write-Host "Lineage:            $LineageId"
    Write-Host "Supervisor process: $(if ($process) { "online (pid $($process.Id))" } else { 'offline' })"
    Write-Host "Supervisor state:   $(if ($state) { [string]$state.state } else { 'not initialized' })"
    if ($state) {
        Write-Host "Reason:             $($state.reason)"
        Write-Host "Current segment:    $(if ($state.currentSegment) { $state.currentSegment } else { 'none' })"
        Write-Host "Updated:            $($state.updatedUtc)"
    }
    Write-Host "Remote Operations:  $(if (Test-Endpoint "$OperationsUrl/health") { 'online' } else { 'offline' })"
}

if ($Action -eq "Status") {
    Show-Status
    exit 0
}

if ($Action -in @("Stop", "EmergencyStop")) {
    Send-Control $(if ($Action -eq "EmergencyStop") { "emergency_stop" } else { "stop_after_action" })
    Write-Host "Safe stop requested for lineage $LineageId. The current semantic action will finish before checkpointing."
    exit 0
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "The project Python environment is missing. Run the normal project setup first."
}
if (Get-TrackedSupervisor) {
    Write-Host "The supervisor for $LineageId is already running."
    Show-Status
    exit 0
}
if (-not (Test-Path -LiteralPath $ManifestPath)) {
    if (-not $InitialState) {
        throw "A new lineage requires -InitialState. Restarts recover from the existing lineage manifest."
    }
    $initialCandidate = if ([System.IO.Path]::IsPathRooted($InitialState)) { $InitialState } else { Join-Path $ProjectRoot $InitialState }
    $resolvedInitialState = (Resolve-Path -LiteralPath $initialCandidate).Path
} else {
    $resolvedInitialState = $InitialState
}
if ($Provider -eq "replay" -and -not $ReplayPath) {
    throw "The replay provider requires -ReplayPath."
}

if (-not $NoOperationsStart -and -not (Test-Endpoint "$OperationsUrl/health")) {
    & (Join-Path $PSScriptRoot "operations.ps1") -Action Start | Out-Host
}
Send-Control "resume"

$arguments = @(
    "scripts\run_segment_supervisor.py",
    "--lineage-id", $LineageId,
    "--supervisor-root", $SupervisorRoot,
    "--provider", $Provider,
    "--max-actions", [string][Math]::Max($MaxActions, 1),
    "--operations-dir", $OperationsDirectory
)
if ($resolvedInitialState) { $arguments += @("--initial-state", $resolvedInitialState) }
if ($Model) { $arguments += @("--model", $Model) }
if ($ReplayPath) {
    $replayCandidate = if ([System.IO.Path]::IsPathRooted($ReplayPath)) { $ReplayPath } else { Join-Path $ProjectRoot $ReplayPath }
    $arguments += @("--replay-path", (Resolve-Path -LiteralPath $replayCandidate).Path)
}
if ($NoVideo) { $arguments += "--no-video" }

$stdout = Join-Path $LogDirectory "$LineageId.out.log"
$stderr = Join-Path $LogDirectory "$LineageId.err.log"
$process = Start-Process -FilePath $Python -ArgumentList $arguments -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
Start-Sleep -Milliseconds 500
if ($process.HasExited) {
    throw "The supervisor exited during startup. Review $stderr."
}
@{
    Id = $process.Id
    LineageId = $LineageId
    StartedUtc = $process.StartTime.ToUniversalTime().ToString("o")
    Provider = $Provider
} | ConvertTo-Json | Set-Content -LiteralPath $ProcessPath -Encoding utf8

Write-Host "Durable supervisor started for lineage $LineageId."
Show-Status
