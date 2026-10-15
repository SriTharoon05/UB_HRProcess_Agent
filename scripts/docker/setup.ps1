param([switch]$SkipTrust)
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Docker
Initialize-Env
Push-Location $PackageRoot
try {
    if (Test-Path 'images.tar') {
        if (-not (Test-Path 'images.sha256')) { throw 'images.sha256 is missing. Obtain the complete exported package.' }
        $expected = (Get-Content 'images.sha256' -Raw).Trim()
        if ((Get-FileHash 'images.tar' -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected.ToLowerInvariant()) { throw 'images.tar checksum mismatch. Transfer the package again.' }
        Invoke-Docker load --input images.tar
    }
    foreach ($image in @('talentmatch-backend:phase1', 'talentmatch-web:phase1', 'redis:7.4-alpine')) {
        Invoke-Docker image inspect $image --format '{{.RepoTags}}'
    }
    New-Item -ItemType Directory -Force '.certs' | Out-Null
    if (-not (Test-Path '.certs/server/localhost-key.pem')) {
        Invoke-Docker run --rm --pull never --user 0:0 --mount "type=bind,src=$((Resolve-Path '.certs').Path),dst=/certs" talentmatch-backend:phase1 python /app/docker/certificates.py /certs
    }
    if (-not $SkipTrust) {
        Import-Certificate -FilePath '.certs/rootCA.pem' -CertStoreLocation 'Cert:\CurrentUser\Root' | Out-Null
        Write-Host 'Trusted the unique local CA for the current Windows user. Restart the browser if it was open.'
    } else {
        Write-Host 'Trust skipped. Import .certs/rootCA.pem into your browser/system trusted roots before LinkedIn sign-in.'
    }
    & (Join-Path $PSScriptRoot 'start.ps1')
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw 'Startup failed.' }
} finally { Pop-Location }
