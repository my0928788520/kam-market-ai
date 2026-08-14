param(
    [ValidatePattern('^[A-Za-z0-9]+$')]
    [string]$Symbol,

    [ValidateSet('regular', 'afterhours')]
    [string]$Session = 'regular',

    [ValidateRange(3, 3600)]
    [int]$RefreshSeconds = 3,

    [ValidateRange(1, 65535)]
    [int]$Port = 8765,

    [switch]$PaperTestArmed
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$envFile = Join-Path $projectRoot '.env'
$sourceRoot = Join-Path $projectRoot 'src'

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Missing .venv\Scripts\python.exe. Install the project environment first.'
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw 'Missing local .env. Fubon credentials must remain local and must not be committed or deployed.'
}

# Support a source checkout even when the package has not been installed into .venv.
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$sourceRoot$([IO.Path]::PathSeparator)$env:PYTHONPATH"
}
else {
    $env:PYTHONPATH = $sourceRoot
}

$arguments = @(
    '-m', 'kam_market_ai.market_data.fubon_live_five_timeframe_dashboard_cli',
    '--live',
    '--env', $envFile,
    '--host', '127.0.0.1',
    '--port', [string]$Port,
    '--refresh-seconds', [string]$RefreshSeconds,
    '--snapshot', (Join-Path $projectRoot 'debug\five_timeframe\live.json'),
    '--chart-history', (Join-Path $projectRoot 'debug\five_timeframe\tmf_60m_history.json'),
    '--chart-history-15m', (Join-Path $projectRoot 'debug\five_timeframe\tmf_15m_history.json'),
    '--open-browser'
)

if ($Symbol) {
    $arguments += @('--symbol', $Symbol)
}

if ($Session -eq 'afterhours') {
    $arguments += @('--session', 'afterhours', '--after-hours')
}

if ($PaperTestArmed) {
    $arguments += @(
        '--paper-test-armed',
        '--paper-journal', (Join-Path $projectRoot 'debug\paper_trading\tmf_live_journal.json')
    )
}

Push-Location $projectRoot
try {
    & $python @arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
