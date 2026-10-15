$ErrorActionPreference = 'Stop'
$PackageRoot = if (Test-Path (Join-Path $PSScriptRoot 'compose.yml')) { $PSScriptRoot } else { (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path }
function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed (exit $LASTEXITCODE). Review the preceding Docker message." }
}
function Assert-Docker {
    Invoke-Docker info --format '{{.OSType}}'
    if ((& docker info --format '{{.OSType}}') -ne 'linux') { throw 'Switch Docker Desktop to Linux containers, then run this command again.' }
    Invoke-Docker compose version --short
}
function Initialize-Env {
    $envPath = Join-Path $PackageRoot '.env'
    if (Test-Path $envPath) {
        $content = [IO.File]::ReadAllText($envPath)
        $normalized = [regex]::Replace($content, '(?m)^(REDIS_URL\s*=\s*redis://)(?:localhost|127\.0\.0\.1)(:6379(?:/\d+)?\s*)$', '${1}redis${2}')
        if ($normalized -ne $content) {
            [IO.File]::WriteAllText($envPath, $normalized, (New-Object Text.UTF8Encoding($false)))
            Write-Host 'Updated local Redis hostname in root .env to the Docker service name redis.'
        }
        return
    }
    $legacy = Join-Path $PackageRoot 'backend/.env'
    if (Test-Path $legacy) {
        $content = [IO.File]::ReadAllText($legacy)
        $content = [regex]::Replace($content, '(?m)^(REDIS_URL\s*=\s*redis://)(?:localhost|127\.0\.0\.1)(:6379(?:/\d+)?\s*)$', '${1}redis${2}')
        [IO.File]::WriteAllText($envPath, $content, (New-Object Text.UTF8Encoding($false)))
        Write-Host 'Copied backend/.env to root .env; local Redis now points to the Compose redis service. Original file unchanged.'
        return
    }
    $example = Join-Path $PackageRoot '.env.example'
    if (-not (Test-Path $example)) { $example = Join-Path $PackageRoot 'deploy/docker/.env.example' }
    Copy-Item $example $envPath
    throw 'Created .env. Fill your HR, LinkedIn, D365, Azure OpenAI and private Blob settings, then run setup again. Never send .env to GitHub.'
}
