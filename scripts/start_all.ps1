[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$suiteRoot = Split-Path -Parent $PSScriptRoot
$suiteRun = Join-Path $suiteRoot '.run'
New-Item -ItemType Directory -Path $suiteRun -Force | Out-Null

function Wait-SuiteHttp {
    param([string]$Url, [string]$Service)
    for ($suiteAttempt = 0; $suiteAttempt -lt 40; $suiteAttempt++) {
        try {
            $suiteResponse = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 1
            if ($suiteResponse.StatusCode -eq 200) { return }
        } catch { Start-Sleep -Milliseconds 300 }
    }
    throw "$Service no responde. Revisa los logs en $suiteRun."
}

function Start-SuiteService {
    param([string]$Name)
    $suiteScript = Join-Path $PSScriptRoot "start_$Name.ps1"
    $suiteProcess = Start-Process -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$suiteScript`"") `
        -WorkingDirectory $suiteRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $suiteRun "$Name.log") `
        -RedirectStandardError (Join-Path $suiteRun "$Name.err.log")
    $suiteProcess.Id | Set-Content -LiteralPath (Join-Path $suiteRun "$Name.pid")
}

$suiteBackendListeners = @(Get-NetTCPConnection -LocalPort 8005 -State Listen -ErrorAction SilentlyContinue)
foreach ($suiteListener in $suiteBackendListeners) {
    $suiteProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($suiteListener.OwningProcess)"
    if (-not $suiteProcess.CommandLine -or
        $suiteProcess.CommandLine.IndexOf($suiteRoot, [StringComparison]::OrdinalIgnoreCase) -lt 0 -or
        $suiteProcess.CommandLine -notmatch 'uvicorn') {
        throw 'El puerto 8005 pertenece a otro proceso. No se ha detenido.'
    }
}
if (-not $suiteBackendListeners) { Start-SuiteService -Name 'backend' }
Wait-SuiteHttp -Url 'http://127.0.0.1:8005/health' -Service 'backend'

$suiteFrontendListeners = @(Get-NetTCPConnection -LocalPort 5175 -State Listen -ErrorAction SilentlyContinue)
$suiteOwnFrontend = @($suiteFrontendListeners | Where-Object {
    $suiteProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($_.OwningProcess)"
    $suiteProcess.CommandLine -and
        $suiteProcess.CommandLine.IndexOf((Join-Path $suiteRoot 'src_vue'), [StringComparison]::OrdinalIgnoreCase) -ge 0 -and
        $suiteProcess.CommandLine -match 'vite'
})
if ($suiteOwnFrontend.Count -gt 0) {
    # Probe the address owned by this app, since another app may use IPv4 on the same port.
    if ($suiteOwnFrontend[0].LocalAddress -like '*:*') {
        $suiteFrontendUrl = 'http://[::1]:5175'
    } else {
        $suiteFrontendUrl = 'http://127.0.0.1:5175'
    }
} else {
    if ($suiteFrontendListeners.Count -gt 0) {
        throw 'El puerto 5175 pertenece a otra app. La API esta lista; no se ha detenido ningun proceso ajeno.'
    }
    Start-SuiteService -Name 'frontend'
    $suiteFrontendUrl = 'http://127.0.0.1:5175'
}
Wait-SuiteHttp -Url "$suiteFrontendUrl/" -Service 'frontend'
Write-Host "Mnemos galery: $suiteFrontendUrl"
Write-Host 'API: http://127.0.0.1:8005/docs'
Write-Host "Logs: $suiteRun"
