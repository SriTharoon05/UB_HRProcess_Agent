param([string]$BuildCaBundle = '')
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Docker
$buildOptions = @()
if ($BuildCaBundle) { $buildOptions = @('--secret', "id=build_ca_bundle,src=$((Resolve-Path $BuildCaBundle).Path)") }
Invoke-Docker build @buildOptions -t talentmatch-backend:phase1 (Join-Path $PackageRoot 'backend')
Invoke-Docker build @buildOptions -t talentmatch-web:phase1 (Join-Path $PackageRoot 'frontend')
Invoke-Docker pull redis:7.4-alpine
Write-Host 'Built backend (API + worker), frontend HTTPS gateway, and Redis images.'
