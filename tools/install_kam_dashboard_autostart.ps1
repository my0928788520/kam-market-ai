param(
    [ValidatePattern('^[A-Za-z0-9]+$')]
    [string]$Symbol = 'TMFH6',

    [ValidateSet('regular', 'afterhours')]
    [string]$Session = 'afterhours',

    [ValidateRange(1, 65535)]
    [int]$Port = 8765,

    [string]$TaskName = 'KAM Paper Trading Watchdog'
)

$ErrorActionPreference = 'Stop'
$watchdog = Join-Path $PSScriptRoot 'watch_fubon_five_timeframe_dashboard.ps1'
if (-not (Test-Path -LiteralPath $watchdog -PathType Leaf)) {
    throw 'KAM watchdog script is missing.'
}

$currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$arguments = @(
    '-NoProfile',
    '-ExecutionPolicy Bypass',
    ('-File "{0}"' -f $watchdog),
    "-Symbol $Symbol",
    "-Session $Session",
    "-Port $Port",
    '-PaperTestArmed',
    '-LineAlerts'
) -join ' '
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description 'KAM Paper Trading dashboard watchdog. Live orders remain disabled.' `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "SUCCESS: '$TaskName' was installed and started for $currentUser."
Write-Host 'SAFETY: Paper Trading and LINE alerts only. Live order capability was not enabled.'
