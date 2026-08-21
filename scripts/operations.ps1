param(
    [ValidateSet("Start", "Stop", "Status", "StartAcceptance")]
    [string]$Action = "Start",
    [ValidateRange(1024, 65535)]
    [int]$UiPort = 3000,
    [switch]$NoDirector,
    [switch]$NoPrivateAccess
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$StateDirectory = Join-Path $ProjectRoot "research\artifacts\operations"
$ProcessFile = Join-Path $StateDirectory "processes.json"
$LogDirectory = Join-Path $StateDirectory "logs"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$NextEntry = Join-Path $ProjectRoot "apps\lab-ui\node_modules\next\dist\bin\next"
$NextEntryRelative = "node_modules\next\dist\bin\next"
$OperationsUrl = "http://127.0.0.1:8766"
$UiUrl = "http://127.0.0.1:$UiPort"

New-Item -ItemType Directory -Force -Path $StateDirectory, $LogDirectory | Out-Null

function Test-Endpoint([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Read-TrackedProcesses {
    if (-not (Test-Path -LiteralPath $ProcessFile)) {
        return @()
    }
    try {
        $value = Get-Content -Raw -LiteralPath $ProcessFile | ConvertFrom-Json
        return @($value)
    } catch {
        return @()
    }
}

function Write-TrackedProcesses([array]$Processes) {
    if ($Processes.Count -eq 0) {
        "[]" | Set-Content -LiteralPath $ProcessFile -Encoding utf8
        return
    }
    @($Processes) | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ProcessFile -Encoding utf8
}

function Test-RemoteOnlyUi {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "$UiUrl/api/director-player" -TimeoutSec 2 | Out-Null
        return $false
    } catch {
        return [int]$_.Exception.Response.StatusCode -eq 404
    }
}

function Test-SchemaEndpoint([string]$Url, [string]$Schema) {
    try {
        $body = Invoke-RestMethod -Uri $Url -TimeoutSec 2
        return [string]$body.schema -eq $Schema
    } catch {
        return $false
    }
}

function Find-TailscaleCommand {
    $command = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    foreach ($candidate in @(
        "C:\Program Files\Tailscale\tailscale.exe",
        "C:\Program Files (x86)\Tailscale\tailscale.exe"
    )) {
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
    }
    return $null
}

function Start-TrackedProcess(
    [string]$Name,
    [string]$FilePath,
    [string[]]$Arguments,
    [string]$WorkingDirectory,
    [hashtable]$Environment = @{}
) {
    $previous = @{}
    foreach ($key in $Environment.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], "Process")
    }
    try {
        $stdout = Join-Path $LogDirectory "$Name.out.log"
        $stderr = Join-Path $LogDirectory "$Name.err.log"
        $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        Start-Sleep -Milliseconds 250
        if ($process.HasExited) {
            throw "$Name exited during startup. Review its Operations log."
        }
    } finally {
        foreach ($key in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable($key, $previous[$key], "Process")
        }
    }
    return [pscustomobject]@{
        Name = $Name
        Id = $process.Id
        StartedUtc = $process.StartTime.ToUniversalTime().ToString("o")
    }
}

function Invoke-OperationsUiBuild([string]$Node) {
    $environment = @{
        POKEMON_OPERATIONS_REMOTE_ONLY = "1"
        OPERATIONS_SERVICE_URL = $OperationsUrl
    }
    $previous = @{}
    foreach ($key in $environment.Keys) {
        $previous[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, [string]$environment[$key], "Process")
    }
    try {
        $stdout = Join-Path $LogDirectory "operations-ui-build.out.log"
        $stderr = Join-Path $LogDirectory "operations-ui-build.err.log"
        $process = Start-Process -FilePath $Node -ArgumentList @($NextEntryRelative, "build") -WorkingDirectory (Join-Path $ProjectRoot "apps\lab-ui") -PassThru -Wait -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
        if ($process.ExitCode -ne 0) {
            throw "The production Operations UI build failed. Review its Operations build log."
        }
    } finally {
        foreach ($key in $environment.Keys) {
            [Environment]::SetEnvironmentVariable($key, $previous[$key], "Process")
        }
    }
}

function Get-ListenerRecord([string]$Name, [int]$Port) {
    $pattern = "^\s*TCP\s+127\.0\.0\.1:$Port\s+.*\s+LISTENING\s+(\d+)\s*$"
    foreach ($line in (netstat -ano -p tcp)) {
        if ($line -notmatch $pattern) {
            continue
        }
        $listenerProcess = Get-Process -Id ([int]$Matches[1]) -ErrorAction SilentlyContinue
        if (-not $listenerProcess) {
            return $null
        }
        return [pscustomobject]@{
            Name = $Name
            Id = $listenerProcess.Id
            StartedUtc = $listenerProcess.StartTime.ToUniversalTime().ToString("o")
        }
    }
    return $null
}

function Add-TrackedRecord([array]$Records, $Record) {
    if ($null -eq $Record -or ($Records | Where-Object { [int]$_.Id -eq [int]$Record.Id })) {
        return @($Records)
    }
    return @($Records) + $Record
}

function Wait-Endpoint([string]$Url, [int]$Seconds = 30) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Endpoint $Url) {
            return
        }
        Start-Sleep -Milliseconds 350
    }
    throw "A local service did not become healthy in time. Review the Operations logs."
}

function Show-Status {
    $operationsHealthy = Test-Endpoint "$OperationsUrl/health"
    $uiHealthy = Test-Endpoint "$UiUrl/operations"
    Write-Host "Operations service: $(if ($operationsHealthy) { 'online' } else { 'offline' })"
    Write-Host "Director sidecar:   $(if (Test-Endpoint 'http://127.0.0.1:8765/health') { 'online' } else { 'offline' })"
    $remoteOnly = $uiHealthy -and (Test-RemoteOnlyUi)
    Write-Host "Operations page:    $(if ($uiHealthy) { 'online' } else { 'offline' })"
    Write-Host "Remote-only guard:  $(if ($remoteOnly) { 'active' } elseif ($uiHealthy) { 'INACTIVE' } else { 'unknown' })"
    if ($uiHealthy) {
        Write-Host "Local page:         $UiUrl/operations"
    }
    $tailscale = Find-TailscaleCommand
    if ($tailscale) {
        Write-Host "Private access:     Tailscale installed (run 'tailscale serve status' for the private URL)"
    } else {
        Write-Host "Private access:     Tailscale is not installed"
    }
}

if ($Action -eq "Status") {
    Show-Status
    exit 0
}

if ($Action -eq "Stop") {
    if (Test-Endpoint "$OperationsUrl/health") {
        try {
            $stopBody = @{ action = "emergency_stop"; source = "operations_launcher_stop" } | ConvertTo-Json
            Invoke-RestMethod -Uri "$OperationsUrl/control" -Method Post -ContentType "application/json" -Body $stopBody | Out-Null
            Start-Sleep -Seconds 1
        } catch {
            Write-Warning "The active run did not acknowledge the launcher stop request; service processes will still be stopped."
        }
    }
    $records = @(Read-TrackedProcesses)
    if (Test-SchemaEndpoint "$OperationsUrl/health" "operations_health_v1") {
        $records = @(Add-TrackedRecord $records (Get-ListenerRecord "operations-service-listener" 8766))
    }
    if ((Test-Endpoint "$UiUrl/operations") -and (Test-RemoteOnlyUi)) {
        $records = @(Add-TrackedRecord $records (Get-ListenerRecord "operations-ui-listener" $UiPort))
    }
    if (Test-SchemaEndpoint "http://127.0.0.1:8765/status" "director_player_status_v1") {
        $records = @(Add-TrackedRecord $records (Get-ListenerRecord "director-player-listener" 8765))
    }
    $remaining = @()
    [Array]::Reverse($records)
    foreach ($record in $records) {
        $process = Get-Process -Id ([int]$record.Id) -ErrorAction SilentlyContinue
        if (-not $process) {
            continue
        }
        try {
            if ($record.StartedUtc -is [DateTime]) {
                $recordStart = ([DateTime]$record.StartedUtc).ToUniversalTime()
            } else {
                $recordStart = [DateTimeOffset]::Parse([string]$record.StartedUtc).UtcDateTime
            }
            $actualStart = $process.StartTime.ToUniversalTime()
            $startDifference = [Math]::Abs(($actualStart - $recordStart).TotalSeconds)
        } catch {
            $startDifference = [double]::PositiveInfinity
        }
        if ($startDifference -gt 1) {
            Write-Warning "Skipped reused process id $($record.Id)."
            $remaining += $record
            continue
        }
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
        try {
            $process.WaitForExit(5000) | Out-Null
        } catch {
            # The tracked child may have exited when its listener or parent stopped.
        }
    }
    Write-TrackedProcesses $remaining
    Write-Host "Pokemon Player Operations processes stopped. Durable controls and run artifacts were preserved."
    exit 0
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "The project Python environment is missing. Run the normal project setup first."
}
if (-not (Test-Path -LiteralPath $NextEntry)) {
    throw "The local UI dependencies are missing. Install the lab UI dependencies first."
}

$tracked = @(Read-TrackedProcesses)
if (-not (Test-Endpoint "$OperationsUrl/health")) {
    $tracked = @(Add-TrackedRecord $tracked (Start-TrackedProcess "operations-service" $Python @("scripts\operations_service.py") $ProjectRoot))
    Write-TrackedProcesses $tracked
    Wait-Endpoint "$OperationsUrl/health"
    $tracked = @(Add-TrackedRecord $tracked (Get-ListenerRecord "operations-service-listener" 8766))
    Write-TrackedProcesses $tracked
}

$controlBody = @{ action = "resume"; source = "operations_launcher" } | ConvertTo-Json
Invoke-RestMethod -Uri "$OperationsUrl/control" -Method Post -ContentType "application/json" -Body $controlBody | Out-Null

if ($Action -eq "StartAcceptance") {
    $tracked = @(Add-TrackedRecord $tracked (Start-TrackedProcess "operations-acceptance" $Python @("scripts\operations_acceptance_run.py") $ProjectRoot))
    Write-TrackedProcesses $tracked
}

if ((Test-Endpoint "$UiUrl/operations") -and -not (Test-RemoteOnlyUi)) {
    throw "Port $UiPort is serving the unrestricted lab UI. Stop that development server before starting private Operations."
}

if (-not (Test-Endpoint "$UiUrl/operations")) {
    $node = (Get-Command node.exe -ErrorAction Stop).Source
    Invoke-OperationsUiBuild $node
    $tracked = @(Add-TrackedRecord $tracked (Start-TrackedProcess "operations-ui" $node @($NextEntryRelative, "start", "--hostname", "127.0.0.1", "--port", [string]$UiPort) (Join-Path $ProjectRoot "apps\lab-ui") @{
        POKEMON_OPERATIONS_REMOTE_ONLY = "1"
        OPERATIONS_SERVICE_URL = $OperationsUrl
    }))
    Write-TrackedProcesses $tracked
    Wait-Endpoint "$UiUrl/operations" 60
    $tracked = @(Add-TrackedRecord $tracked (Get-ListenerRecord "operations-ui-listener" $UiPort))
    Write-TrackedProcesses $tracked
    if (-not (Test-RemoteOnlyUi)) {
        throw "The Operations UI started without its remote-only guard. It will not be exposed privately."
    }
}

if (-not $NoDirector -and $Action -ne "StartAcceptance" -and -not (Test-Endpoint "http://127.0.0.1:8765/health")) {
    $rom = Join-Path $ProjectRoot "research\PokemonRed.gb"
    if (Test-Path -LiteralPath $rom) {
        $tracked = @(Add-TrackedRecord $tracked (Start-TrackedProcess "director-player" $Python @("scripts\director_player.py", "--window", "null", "--render", "true") $ProjectRoot))
        Write-TrackedProcesses $tracked
        Wait-Endpoint "http://127.0.0.1:8765/health" 30
        $tracked = @(Add-TrackedRecord $tracked (Get-ListenerRecord "director-player-listener" 8765))
        Write-TrackedProcesses $tracked
    } else {
        Write-Warning "The Director player was not started because the local ROM is unavailable. The Operations page and acceptance fixture still work."
    }
}

Write-TrackedProcesses $tracked

if (-not $NoPrivateAccess) {
    $tailscale = Find-TailscaleCommand
    if ($tailscale) {
        try {
            & $tailscale serve --bg $UiUrl | Out-Host
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Tailscale Serve did not start. Local Operations remains available."
            }
        } catch {
            Write-Warning "Tailscale Serve did not start. Local Operations remains available."
        }
    } else {
        Write-Warning "Tailscale is not installed, so phone access was not configured. Local Operations is running."
    }
}

Show-Status
