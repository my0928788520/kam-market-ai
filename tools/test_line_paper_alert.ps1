param()

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$envFile = Join-Path $projectRoot '.env'
$sourceRoot = Join-Path $projectRoot 'src'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Missing .venv\Scripts\python.exe. Install the project environment first.'
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw 'Missing local .env. LINE credentials must remain local.'
}

if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$sourceRoot$([IO.Path]::PathSeparator)$env:PYTHONPATH"
}
else {
    $env:PYTHONPATH = $sourceRoot
}

Push-Location $projectRoot
try {
    & $python -m kam_market_ai.notifications.line_alert_test_cli --env $envFile --send-test
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
