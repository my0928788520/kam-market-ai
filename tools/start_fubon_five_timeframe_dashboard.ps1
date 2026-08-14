param(
    [ValidatePattern('^[A-Za-z0-9]+$')]
    [string]$Symbol,

    [ValidateSet('regular', 'afterhours')]
    [string]$Session = 'regular',

    [ValidateRange(15, 3600)]
    [int]$RefreshSeconds = 60,

    [ValidateRange(1, 65535)]
    [int]$Port = 8765
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$envFile = Join-Path $projectRoot '.env'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Missing .venv\Scripts\python.exe. Install the project environment first.'
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw 'Missing local .env. Fubon credentials must remain local and must not be committed or deployed.'
}

$arguments = @(
    '-m', 'kam_market_ai.market_data.fubon_live_five_timeframe_dashboard_cli',
    '--live',
    '--env', $envFile,
    '--host', '127.0.0.1',
    '--port', [string]$Port,
    '--refresh-seconds', [string]$RefreshSeconds,
    '--snapshot', (Join-Path $projectRoot 'debug\five_timeframe\live.json'),
    '--open-browser'
)

if ($Symbol) {
    $arguments += @('--symbol', $Symbol)
}

if ($Session -eq 'afterhours') {
    $arguments += @('--session', 'afterhours', '--after-hours')
}

Push-Location $projectRoot
try {
    & $python @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
