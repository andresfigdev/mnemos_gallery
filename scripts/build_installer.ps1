[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$suiteRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $suiteRoot 'venv\Scripts\python.exe'
$specPath = Join-Path $suiteRoot 'packaging\mnemos_backend.spec'
$backendDist = Join-Path $suiteRoot 'build\backend-package'
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

    $electronRoot = Join-Path $frontendRoot 'node_modules\electron'
    $electronDist = Join-Path $electronRoot 'dist'
    $electronExe = Join-Path $electronDist 'electron.exe'
    if (-not (Test-Path -LiteralPath $electronExe)) {
        Push-Location $electronRoot
        try {
            node.exe install.js
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo descargar Electron.' }
        } finally {
            Pop-Location
        }
    }

    npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo compilar Electron.' }

    $builderArgs = @(
        'electron-builder',
        '--win',
        'nsis',
        '--config.electronDist=node_modules/electron/dist'
    )
    npx.cmd @builderArgs
    if ($LASTEXITCODE -ne 0 -and [string]::IsNullOrWhiteSpace($env:ELECTRON_BUILDER_BINARIES_MIRROR)) {
        Write-Warning 'La descarga oficial fallo. Reintentando desde el mirror alternativo verificado...'
        $env:ELECTRON_BUILDER_BINARIES_MIRROR = 'https://npmmirror.com/mirrors/electron-builder-binaries/'
        npx.cmd @builderArgs
    }
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar el instalador.' }
} finally {
    Pop-Location
}

Write-Host "Instalador generado en $frontendRoot\release"
