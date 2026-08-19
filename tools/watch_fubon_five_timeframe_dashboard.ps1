param(
    [ValidatePattern('^[A-Za-z0-9]+$')]
    [string]$Symbol,

    [ValidateSet('regular', 'afterhours')]
    [string]$Session = 'afterhours',

    [ValidateRange(1, 65535)]
    [int]$Port = 8765,

    [ValidateRange(10, 300)]
    [int]$CheckSeconds = 30,

    [switch]$PaperTestArmed,

    [switch]$LineAlerts,

    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dashboardScript = Join-Path $PSScriptRoot 'start_fubon_five_timeframe_dashboard.ps1'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$envFile = Join-Path $projectRoot '.env'
$healthUrl = "http://127.0.0.1:$Port/api/five-timeframe/health"
$logDirectory = Join-Path $projectRoot 'debug\watchdog'
$stdoutLog = Join-Path $logDirectory 'dashboard.stdout.log'
$stderrLog = Join-Path $logDirectory 'dashboard.stderr.log'
$mutexName = "Local\KAM.FiveTimeframe.Watchdog.$Port"
$mutex = New-Object System.Threading.Mutex($false, $mutexName)
$hasMutex = $false
$dashboardProcess = $null
$consecutiveFailures = 0
$restartInProgress = $false

function Test-DashboardHealth {
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 5
        return ($null -ne $response)
    }
    catch {
        return $false
    }
}

function Get-LocalEnvValue {
    param([Parameter(Mandatory = $true)][string]$Name)
    $envFile = Join-Path $projectRoot '.env'
    if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
        return $null
    }
    foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }
        $parts = $trimmed.Split('=', 2)
        if ($parts.Count -eq 2 -and $parts[0].Trim() -eq $Name) {
            return $parts[1].Trim()
        }
    }
    return $null
}

function Send-LineRecoveryNotice {
    if (-not $LineAlerts) {
        return
    }
    $token = Get-LocalEnvValue -Name 'KAM_LINE_CHANNEL_ACCESS_TOKEN'
    $recipient = Get-LocalEnvValue -Name 'KAM_LINE_RECIPIENT_USER_ID'
    if (-not $token -or -not $recipient) {
        return
    }
    try {
        $noticeArguments = @(
            '-m', 'kam_market_ai.notifications.watchdog_recovery_cli',
            '--env', $envFile,
            '--session', $Session,
            '--health-url', $healthUrl
        )
        if ($Symbol) {
            $noticeArguments += @('--symbol', $Symbol)
        }
        & $python @noticeArguments | Out-Null
    catch {
        # The next healthy dashboard cycle still provides its own persistent LINE recovery notice.
    }
}

function Start-DashboardProcess {
    if (-not (Test-Path -LiteralPath $dashboardScript -PathType Leaf)) {
        throw 'Dashboard start script is missing.'
    }
    New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
    $arguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', ('"{0}"' -f $dashboardScript),
        '-Session', $Session,
        '-Port', [string]$Port
    )
    if ($Symbol) {
        $arguments += @('-Symbol', $Symbol)
    }
    if ($PaperTestArmed) {
        $arguments += '-PaperTestArmed'
    }
    if ($LineAlerts) {
        if (-not $PaperTestArmed) {
            throw 'LineAlerts requires PaperTestArmed.'
        }
        $arguments += '-LineAlerts'
    }
    if ($NoBrowser) {
        $arguments += '-NoBrowser'
    }
    return Start-Process `
        -FilePath 'powershell.exe' `
        -ArgumentList $arguments `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog `
        -PassThru
}

function Stop-ProjectDashboardProcesses {
    $escapedName = [Regex]::Escape((Split-Path -Leaf $dashboardScript))
    $processes = Get-CimInstance Win32_Process -Filter "Name = 'powershell.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine -match $escapedName }
    foreach ($process in $processes) {
        & taskkill.exe /PID $process.ProcessId /T /F 2>$null | Out-Null
    }
}

try {
    $hasMutex = $mutex.WaitOne(0, $false)
    if (-not $hasMutex) {
        Write-Host 'KAM watchdog is already running. No duplicate instance was started.'
        exit 0
    }
    if (-not (Test-DashboardHealth)) {
        $dashboardProcess = Start-DashboardProcess
        $restartInProgress = $true
    }
    while ($true) {
        Start-Sleep -Seconds $CheckSeconds
        if (Test-DashboardHealth) {
            $consecutiveFailures = 0
            if ($restartInProgress) {
                Send-LineRecoveryNotice
                $restartInProgress = $false
            }
            continue
        }
        $consecutiveFailures += 1
        if ($consecutiveFailures -lt 3) {
            continue
        }
        Stop-ProjectDashboardProcesses
        $dashboardProcess = Start-DashboardProcess
        $restartInProgress = $true
        $consecutiveFailures = 0
    }
}
finally {
    if ($hasMutex) {
        $mutex.ReleaseMutex()
    }
    $mutex.Dispose()
}
