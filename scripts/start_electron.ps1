[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$suiteRoot = Split-Path -Parent $PSScriptRoot
$suiteRun = Join-Path $suiteRoot '.run'
$frontendRoot = Join-Path $suiteRoot 'src_vue'
New-Item -ItemType Directory -Path $suiteRun -Force | Out-Null

function Test-SuiteProcess {
    param($ProcessInfo)
    if (-not $ProcessInfo) { return $false }
    $commandLine = [string]$ProcessInfo.CommandLine
    $executable = [string]$ProcessInfo.ExecutablePath
    return (
        $commandLine.IndexOf($suiteRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        $executable.IndexOf($suiteRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
    )
}

function Stop-SuiteListener {
    param([int]$Port, [string]$ExpectedPattern)
    $listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if (-not (Test-SuiteProcess $processInfo) -or $processInfo.CommandLine -notmatch $ExpectedPattern) {
            throw "El puerto $Port pertenece a otro proceso. No se ha detenido."
        }
        Stop-Process -Id $listener.OwningProcess -Force
    }
}

function Wait-SuiteHttp {
    param([string]$Url, [string]$Service)
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 1
            if ($response.StatusCode -eq 200) { return }
        } catch { Start-Sleep -Milliseconds 300 }
    }
    throw "$Service no responde. Revisa los logs en $suiteRun."
}

function Start-SuiteScript {
    param([string]$Name, [string]$ScriptName)
    $scriptPath = Join-Path $PSScriptRoot $ScriptName
    $process = Start-Process -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$scriptPath`"") `
        -WorkingDirectory $suiteRoot `
        -WindowStyle Hidden `
        -PassThru `
        -RedirectStandardOutput (Join-Path $suiteRun "$Name.log") `
        -RedirectStandardError (Join-Path $suiteRun "$Name.err.log")
    $process.Id | Set-Content -LiteralPath (Join-Path $suiteRun "$Name.pid")
}

Write-Host 'Cerrando procesos anteriores de Mnemos galery...'
Stop-SuiteListener -Port 8005 -ExpectedPattern 'uvicorn'
Stop-SuiteListener -Port 5175 -ExpectedPattern 'vite'

# Cerrar Electron y auxiliares Node que pertenezcan a este proyecto.
$suiteProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    (Test-SuiteProcess $_) -and (
        $_.Name -ieq 'electron.exe' -or
        ($_.Name -ieq 'node.exe' -and $_.CommandLine -match 'concurrently|wait-on|vite|electron')
    )
})
foreach ($processInfo in $suiteProcesses) {
    Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction SilentlyContinue
}

for ($attempt = 0; $attempt -lt 20; $attempt++) {
    $backendBusy = Get-NetTCPConnection -LocalPort 8005 -State Listen -ErrorAction SilentlyContinue
    $frontendBusy = Get-NetTCPConnection -LocalPort 5175 -State Listen -ErrorAction SilentlyContinue
    if (-not $backendBusy -and -not $frontendBusy) { break }
    Start-Sleep -Milliseconds 250
}

Write-Host 'Iniciando backend...'
Start-SuiteScript -Name 'backend' -ScriptName 'start_backend.ps1'
Wait-SuiteHttp -Url 'http://127.0.0.1:8005/health' -Service 'Backend'

Write-Host 'Iniciando Vite + Electron...'
Start-SuiteScript -Name 'electron' -ScriptName 'start_frontend.ps1'
Wait-SuiteHttp -Url 'http://127.0.0.1:5175/' -Service 'Frontend'

$electronReady = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    $electronProcesses = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -ieq 'electron.exe' -and (Test-SuiteProcess $_)
    })
    if ($electronProcesses.Count -gt 0) {
        $electronReady = $true
        break
    }
    Start-Sleep -Milliseconds 300
}
if (-not $electronReady) {
    throw "Electron no abrió una ventana. Revisa $suiteRun\electron.err.log."
}

Write-Host 'Mnemos galery está ejecutándose en Electron.'
Write-Host 'API: http://127.0.0.1:8005/docs'
Write-Host "Logs: $suiteRun"

