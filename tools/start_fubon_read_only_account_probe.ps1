param(
    [ValidateSet('hybrid', 'single')]
    [string]$Method = 'hybrid',

    [ValidateRange(5, 120)]
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$envFile = Join-Path $projectRoot '.env'
$probe = Join-Path $projectRoot 'tools\probe_fubon_position.py'
$output = Join-Path $projectRoot 'debug\position\probe_result.json'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Missing .venv\Scripts\python.exe. Install the project environment first.'
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw 'Missing local .env. Configure Fubon credentials and certificate first.'
}
if (-not (Test-Path -LiteralPath $probe -PathType Leaf)) {
    throw 'Missing the read-only account probe.'
}

Write-Host 'Starting Fubon read-only account probe. No order can be placed, modified, or cancelled.'
Push-Location $projectRoot
try {
    & $python $probe --live --method $Method --timeout $TimeoutSeconds --output $output
    $probeExitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
        throw 'The probe did not create a safe result file.'
    }

    $result = Get-Content -LiteralPath $output -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($probeExitCode -eq 0 -and $result.status -eq 'completed') {
        $rowCount = $result.summary.data_row_count
        Write-Host "SUCCESS: Login and read-only futures position query completed. Row count: $rowCount."
        Write-Host 'SAFETY: Query only. Live order capability is not available.'
        exit 0
    }

    $reason = if ($result.status -eq 'timeout') { 'TIMEOUT' } elseif ($result.exception_type) { $result.exception_type } else { 'UNKNOWN_ERROR' }
    Write-Error "FAILED: $reason. Output is redacted. Never share .env or certificate contents."
    exit 1
}
finally {
    Pop-Location
}
