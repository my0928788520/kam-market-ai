param(
    [string]$TaskName = 'KAM Paper Trading Watchdog'
)

$ErrorActionPreference = 'Stop'
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "No scheduled task named '$TaskName' exists."
    exit 0
}

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "SUCCESS: '$TaskName' was removed."
Write-Host 'Existing Paper Trading journals and LINE delivery history were preserved.'
