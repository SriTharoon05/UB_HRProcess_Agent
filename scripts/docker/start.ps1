. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Docker
Initialize-Env
if (-not (Test-Path (Join-Path $PackageRoot '.certs/server/localhost-key.pem'))) { throw 'Run setup.ps1 once to create this computer''s localhost certificates.' }
Push-Location $PackageRoot
try {
    Invoke-Docker compose --env-file .env -f compose.yml up -d --wait --wait-timeout 180 --no-build --pull never
    Write-Host 'TalentMatch is ready at https://localhost:7242'
    Write-Host 'LinkedIn callback: https://localhost:7242/auth/linkedin/callback'
    Write-Host 'Next time: Docker Desktop > Containers > talentmatch > Start (group Play button).'
    Write-Host 'After editing .env, rerun start.ps1 to apply settings; group Play alone keeps the existing settings.'
} finally { Pop-Location }
