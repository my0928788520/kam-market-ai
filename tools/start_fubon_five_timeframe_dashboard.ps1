param(
    [ValidatePattern('^[A-Za-z0-9]+$')]
    [string]$Symbol,

    [ValidateSet('regular', 'afterhours')]
    [string]$Session = 'regular',

    [ValidateRange(3, 3600)]
    [int]$RefreshSeconds = 3,

    [ValidateRange(1, 65535)]
    [int]$Port = 8765,

    [switch]$PaperTestArmed,

    [switch]$LineAlerts,

    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$envFile = Join-Path $projectRoot '.env'
$sourceRoot = Join-Path $projectRoot 'src'

$productCode = 'TMF'
if ($Symbol) {
    $normalizedSymbol = $Symbol.ToUpperInvariant()
    if ($normalizedSymbol.StartsWith('TXF')) {
        $productCode = 'TX'
    }
    elseif ($normalizedSymbol.StartsWith('MXF')) {
        $productCode = 'MTX'
    }
    elseif (-not $normalizedSymbol.StartsWith('TMF')) {
        throw 'Symbol must begin with TXF, MXF, or TMF.'
    }
}
$productSlug = $productCode.ToLowerInvariant()

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
    '--instrument', $productCode,
    '--snapshot', (Join-Path $projectRoot "debug\five_timeframe\${productSlug}_live.json"),
    '--chart-history', (Join-Path $projectRoot "debug\five_timeframe\${productSlug}_60m_history.json"),
    '--chart-history-15m', (Join-Path $projectRoot "debug\five_timeframe\${productSlug}_15m_history.json"),
    '--taifex-history-cache', (Join-Path $projectRoot "debug\five_timeframe\${productSlug}_taifex_official_history.json"),
    '--taiex-weekly-cache', (Join-Path $projectRoot "debug\five_timeframe\taiex_official_weekly.json")
)

if (-not $NoBrowser) {
    $arguments += '--open-browser'
}

if ($Symbol) {
    $arguments += @('--symbol', $Symbol)
}

if ($Session -eq 'afterhours') {
    $arguments += @('--session', 'afterhours', '--after-hours')
}

if ($PaperTestArmed) {
    $arguments += @(
        '--paper-test-armed',
        '--paper-journal', (Join-Path $projectRoot "debug\paper_trading\${productSlug}_live_journal.json")
    )
}

if ($LineAlerts) {
    if (-not $PaperTestArmed) {
        throw 'LineAlerts requires PaperTestArmed.'
    }
    $arguments += @(
        '--line-alerts',
        '--line-alert-state', (Join-Path $projectRoot "debug\notifications\${productSlug}_line_delivery.json")
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
