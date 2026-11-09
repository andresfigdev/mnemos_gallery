[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$suiteRoot = Split-Path -Parent $PSScriptRoot
$suitePython = Join-Path $suiteRoot 'venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $suitePython)) {
    throw 'No existe venv\Scripts\python.exe. Prepara el entorno Python primero.'
}

Push-Location $suiteRoot
try {
    & $suitePython -X utf8 -c 'import uvicorn'
    if ($LASTEXITCODE -ne 0) { throw 'Falta uvicorn. Instala requirements.txt con el Python de venv.' }
    Write-Host 'Mnemos galery API: http://127.0.0.1:8005/docs'
    & $suitePython -X utf8 -m uvicorn src_python.main:app --app-dir $suiteRoot --host 127.0.0.1 --port 8005
    if ($LASTEXITCODE -ne 0) { throw 'La API no pudo arrancar. Revisa el error anterior.' }
} finally { Pop-Location }
