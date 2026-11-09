[CmdletBinding()]
param(
    [switch]$WithBuildTools
)

$ErrorActionPreference = 'Stop'
$suiteRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $suiteRoot 'venv'
$pythonPath = Join-Path $venvPath 'Scripts\python.exe'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python no está instalado o no está disponible en PATH.'
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    python -m venv $venvPath
}

& $pythonPath -m pip install --upgrade pip
& $pythonPath -m pip install -r (Join-Path $suiteRoot 'requirements.txt')
if ($WithBuildTools) {
    & $pythonPath -m pip install -r (Join-Path $suiteRoot 'requirements-build.txt')
}

Write-Host 'Entorno Python preparado correctamente.'
