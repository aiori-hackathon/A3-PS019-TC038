param(
    [switch]$Build,
    # Interface to listen on. 'localhost' keeps the app private to this machine;
    # use 0.0.0.0 to expose it on the network (only behind authentication).
    [string]$BindHost = $(if ($env:PRIVACYTWIN_HOST) { $env:PRIVACYTWIN_HOST } else { 'localhost' }),
    [int]$ApiPort = $(if ($env:PRIVACYTWIN_API_PORT) { [int]$env:PRIVACYTWIN_API_PORT } else { 8000 }),
    [int]$WebPort = $(if ($env:PORT) { [int]$env:PORT } else { 3000 })
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$webRoot = Join-Path $projectRoot 'web'
$runtimeRoot = Join-Path $projectRoot 'data\runtime'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Python environment missing. Follow the setup steps in README.md.' }
if (-not (Test-Path -LiteralPath (Join-Path $webRoot 'node_modules'))) { throw 'Frontend dependencies missing. Run npm ci in web first.' }
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null

# A wildcard bind address is not reachable as a URL; probe it through the loopback name instead.
$probeHost = if ($BindHost -in @('0.0.0.0', '::', '*')) { 'localhost' } else { $BindHost }
$apiUrl = if ($env:PRIVACYTWIN_API_URL) { $env:PRIVACYTWIN_API_URL } else { "http://${probeHost}:$ApiPort" }
$webUrl = "http://${probeHost}:$WebPort"

# The /api proxy target is fixed at build time, so rebuild whenever it changes.
$apiUrlFile = Join-Path $runtimeRoot 'api-url.txt'
$builtFor = if (Test-Path -LiteralPath $apiUrlFile) { (Get-Content -LiteralPath $apiUrlFile -Raw).Trim() } else { '' }
if ($Build -or $builtFor -ne $apiUrl -or -not (Test-Path -LiteralPath (Join-Path $webRoot '.next\BUILD_ID'))) {
    Push-Location $webRoot
    try {
        $env:PRIVACYTWIN_API_URL = $apiUrl
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
        Set-Content -LiteralPath $apiUrlFile -Value $apiUrl
    }
    finally { Pop-Location }
}

$health = $null
try { $health = Invoke-RestMethod "$apiUrl/api/health" -TimeoutSec 2 } catch {}
if ($health -and $health.version -ne '2.0.0') { throw "$apiUrl is serving an older or different app. Stop it before starting PrivacyTwin." }
if (-not $health) {
    $backend = Start-Process -FilePath $pythonPath -ArgumentList '-m','uvicorn','main:app','--host',$BindHost,'--port',"$ApiPort" -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'backend.log') -RedirectStandardError (Join-Path $runtimeRoot 'backend.error.log') -PassThru
    @{ id = $backend.Id; started = $backend.StartTime.Ticks; name = $backend.ProcessName } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot 'backend.process.json')
}
$frontend = $null
try { $frontend = Invoke-RestMethod "$webUrl/api/health" -TimeoutSec 2 } catch {}
if ($frontend -and $frontend.version -ne '2.0.0') { throw "$webUrl is serving a different app." }
if (-not $frontend) {
    $nodePath = (Get-Command node.exe).Source
    $nextPath = Join-Path $webRoot 'node_modules\next\dist\bin\next'
    $frontendProcess = Start-Process -FilePath $nodePath -ArgumentList ('"' + $nextPath + '"'),'start','--hostname',$BindHost,'--port',"$WebPort" -WorkingDirectory $webRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $runtimeRoot 'frontend.log') -RedirectStandardError (Join-Path $runtimeRoot 'frontend.error.log') -PassThru
    @{ id = $frontendProcess.Id; started = $frontendProcess.StartTime.Ticks; name = $frontendProcess.ProcessName } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimeRoot 'frontend.process.json')
}
Write-Output "PrivacyTwin: $webUrl"
Write-Output "Logs: $runtimeRoot"
