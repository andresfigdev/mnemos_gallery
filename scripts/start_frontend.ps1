[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$suiteRoot = Split-Path -Parent $PSScriptRoot
Push-Location (Join-Path $suiteRoot 'src_vue')
try {
    npm.cmd run dev:electron
    if ($LASTEXITCODE -ne 0) { throw 'El frontend no pudo arrancar.' }
} finally { Pop-Location }
