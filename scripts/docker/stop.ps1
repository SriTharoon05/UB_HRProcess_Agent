. (Join-Path $PSScriptRoot 'common.ps1')
Push-Location $PackageRoot
try { Invoke-Docker compose --env-file .env -f compose.yml stop } finally { Pop-Location }
