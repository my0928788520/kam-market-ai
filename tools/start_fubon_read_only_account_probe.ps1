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
    throw '找不到 .venv\Scripts\python.exe，請先安裝專案環境。'
}
if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
    throw '找不到本機 .env，請先設定富邦登入資料與憑證。'
}
if (-not (Test-Path -LiteralPath $probe -PathType Leaf)) {
    throw '找不到帳戶唯讀測試程式。'
}

Write-Host '開始富邦帳戶唯讀連線測試；不會送出、修改或取消任何委託。'
Push-Location $projectRoot
try {
    & $python $probe --live --method $Method --timeout $TimeoutSeconds --output $output
    $probeExitCode = $LASTEXITCODE
    if (-not (Test-Path -LiteralPath $output -PathType Leaf)) {
        throw '測試未產生安全結果檔。'
    }

    $result = Get-Content -LiteralPath $output -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($probeExitCode -eq 0 -and $result.status -eq 'completed') {
        $rowCount = $result.summary.data_row_count
        Write-Host "測試成功：帳戶已登入，期貨部位唯讀查詢完成；回傳筆數 $rowCount。"
        Write-Host '安全限制仍有效：僅查詢，不具備真實下單能力。'
        exit 0
    }

    $reason = if ($result.status -eq 'timeout') { '連線逾時' } elseif ($result.exception_type) { $result.exception_type } else { '未知錯誤' }
    Write-Error "測試失敗：$reason。結果已安全去識別化，請勿貼出 .env 或憑證內容。"
    exit 1
}
finally {
    Pop-Location
}
