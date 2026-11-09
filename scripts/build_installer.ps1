[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$suiteRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $suiteRoot 'venv\Scripts\python.exe'
$specPath = Join-Path $suiteRoot 'packaging\mnemos_backend.spec'
$backendDist = Join-Path $suiteRoot 'build\backend'
$backendWork = Join-Path $suiteRoot 'build\pyinstaller'
$frontendRoot = Join-Path $suiteRoot 'src_vue'

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Falta venv. Ejecuta .\scripts\setup_venv.ps1 -WithBuildTools.'
}

& $pythonPath -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Falta PyInstaller. Ejecuta .\scripts\setup_venv.ps1 -WithBuildTools.'
}

New-Item -ItemType Directory -Path $backendDist -Force | Out-Null
& $pythonPath -m PyInstaller --noconfirm --clean `
    --distpath $backendDist `
    --workpath $backendWork `
    $specPath
if ($LASTEXITCODE -ne 0) { throw 'No se pudo empaquetar el backend.' }

Push-Location $frontendRoot
try {
    npm.cmd ci
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias del frontend.' }
    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar Electron.' }
    npx.cmd electron-builder --win nsis
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar el instalador.' }
} finally {
    Pop-Location
}

Write-Host "Instalador generado en $frontendRoot\release"
