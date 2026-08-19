param(
    [ValidatePattern('^[A-Za-z0-9]+$')]
    [string]$Symbol = 'TMFI6',

    [ValidateRange(1, 65535)]
    [int]$Port = 8765,

    [ValidateRange(30, 300)]
    [int]$StartupTimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$watchdogScript = Join-Path $PSScriptRoot 'watch_fubon_five_timeframe_dashboard.ps1'
$healthUrl = "http://127.0.0.1:$Port/api/five-timeframe/health"
$dashboardUrl = "http://127.0.0.1:$Port/"
$launcherLogDirectory = Join-Path $projectRoot 'debug\launcher'
$watchdogOutput = Join-Path $launcherLogDirectory 'watchdog.stdout.log'
$watchdogError = Join-Path $launcherLogDirectory 'watchdog.stderr.log'

function Get-KamSession {
    $taipeiZone = [TimeZoneInfo]::FindSystemTimeZoneById('Taipei Standard Time')
    $taipeiNow = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $taipeiZone)
    $minuteOfDay = ($taipeiNow.Hour * 60) + $taipeiNow.Minute
    $regularStart = (8 * 60) + 45
    $regularEnd = (13 * 60) + 45
    if ($minuteOfDay -ge $regularStart -and $minuteOfDay -lt $regularEnd) {
        return 'regular'
    }
    return 'afterhours'
}

function Stop-OldKamProcesses {
    $processes = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -match '^(python|pythonw|powershell)\.exe$' -and
            $_.CommandLine -and (
                $_.CommandLine -match 'fubon_live_five_timeframe_dashboard_cli' -or
                $_.CommandLine -match 'watch_fubon_five_timeframe_dashboard\.ps1'
            )
        }
    foreach ($process in $processes) {
        if ($process.ProcessId -ne $PID) {
            Start-Process `
                -FilePath 'taskkill.exe' `
                -ArgumentList @('/PID', [string]$process.ProcessId, '/T', '/F') `
                -WindowStyle Hidden `
                -Wait `
                -ErrorAction SilentlyContinue | Out-Null
        }
    }

    Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        Where-Object { $_ -and $_ -ne $PID } |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
}

function Test-KamHealth {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 5
        return ($health.success -eq $true -and $health.market_data_only -eq $true -and $health.live_order_allowed -eq $false)
    }
    catch {
        return $false
    }
}

if (-not (Test-Path -LiteralPath $watchdogScript -PathType Leaf)) {
    throw 'KAM watchdog script is missing.'
}

New-Item -ItemType Directory -Path $launcherLogDirectory -Force | Out-Null
$session = Get-KamSession
Write-Host "KAM_STARTING | symbol=$Symbol | session=$session | port=$Port" -ForegroundColor Cyan
Write-Host 'KAM_SAFETY | Paper Trading only | live orders disabled' -ForegroundColor Yellow

Stop-OldKamProcesses
Start-Sleep -Seconds 2

$watchdogArguments = @(
    '-NoProfile',
    '-ExecutionPolicy', 'Bypass',
    '-File', ('"{0}"' -f $watchdogScript),
    '-Symbol', $Symbol,
    '-Session', $session,
    '-Port', [string]$Port,
    '-CheckSeconds', '15',
    '-StartupGraceSeconds', '180',
    '-PaperTestArmed',
    '-NoBrowser'
)

$watchdog = Start-Process `
    -FilePath 'powershell.exe' `
    -ArgumentList $watchdogArguments `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $watchdogOutput `
    -RedirectStandardError $watchdogError `
    -PassThru

$deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
do {
    if (Test-KamHealth) {
        Write-Host 'KAM_READY | health check passed | opening dashboard' -ForegroundColor Green
        Start-Process $dashboardUrl
        Write-Host "KAM_URL | $dashboardUrl"
        Write-Host "KAM_WATCHDOG_PID | $($watchdog.Id)"
        exit 0
    }
    if ($watchdog.HasExited) {
        $detail = if (Test-Path -LiteralPath $watchdogError) {
            (Get-Content -LiteralPath $watchdogError -Tail 12 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
        }
        else { 'No watchdog error log was created.' }
        throw "KAM watchdog exited before startup completed.$([Environment]::NewLine)$detail"
    }
    Write-Host 'KAM_WAITING | initializing data and health endpoint...'
    Start-Sleep -Seconds 3
} while ([DateTime]::UtcNow -lt $deadline)

$errorDetail = if (Test-Path -LiteralPath $watchdogError) {
    (Get-Content -LiteralPath $watchdogError -Tail 12 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
}
else { 'No startup error was written.' }
throw "KAM startup timed out after $StartupTimeoutSeconds seconds.$([Environment]::NewLine)$errorDetail"
