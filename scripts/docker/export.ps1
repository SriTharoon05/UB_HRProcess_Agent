param([string]$OutputDirectory = '', [switch]$Build, [string]$BuildCaBundle = '')
. (Join-Path $PSScriptRoot 'common.ps1')
Assert-Docker
if ($Build) { & (Join-Path $PSScriptRoot 'build.ps1') -BuildCaBundle $BuildCaBundle }
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $PackageRoot 'dist/talentmatch' }
$target = [IO.Path]::GetFullPath($OutputDirectory)
if ($target -eq $PackageRoot) { throw 'Export to a separate directory, for example dist/talentmatch.' }
New-Item -ItemType Directory -Force $target | Out-Null
Copy-Item (Join-Path $PackageRoot 'compose.yml') (Join-Path $target 'compose.yml')
Copy-Item (Join-Path $PackageRoot 'deploy/docker/.env.example') (Join-Path $target '.env.example')
foreach ($name in @('common.ps1','setup.ps1','setup.cmd','start.ps1','start.cmd','stop.ps1','stop.cmd','common.sh','setup.sh','start.sh','stop.sh')) {
    Copy-Item (Join-Path $PSScriptRoot $name) (Join-Path $target $name)
}
$docs = Join-Path $PackageRoot 'docs'
if (Test-Path $docs) {
    $docsTarget = Join-Path $target 'docs'
    New-Item -ItemType Directory -Force $docsTarget | Out-Null
    Copy-Item (Join-Path $docs '*') -Destination $docsTarget -Recurse -Force
}
$instructions = @'
# TalentMatch portable runtime

Start with [Docker setup and transfer instructions](docs/docker-local.md).

- [Supabase migration and environment settings](docs/supabase.md)
- [Technical reference (Word)](docs/reference/AI-Powered%20HR%20Recruitment%20Process%20Using%20D365%20-%20Technical%20Document.docx)
- [Business reference (Word)](docs/reference/AI-Powered%20HR%20Recruitment%20Process%20Using%20D365-%20Business%20Document.docx)

Put your private .env beside compose.yml. Run setup.cmd once on Windows or ./setup.sh on Linux/macOS.
After initial setup, use Docker Desktop > Containers > talentmatch > Play.
Open https://localhost:7242. The LinkedIn callback is https://localhost:7242/auth/linkedin/callback.
'@
[IO.File]::WriteAllText((Join-Path $target 'Docker instructions.md'), $instructions, (New-Object Text.UTF8Encoding($false)))
Invoke-Docker save --output (Join-Path $target 'images.tar') talentmatch-backend:phase1 talentmatch-web:phase1 redis:7.4-alpine
$hash = (Get-FileHash (Join-Path $target 'images.tar') -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText((Join-Path $target 'images.sha256'), "$hash`n", (New-Object Text.UTF8Encoding($false)))
$platform = & docker image inspect talentmatch-backend:phase1 --format '{{.Os}}/{{.Architecture}}'
[IO.File]::WriteAllText((Join-Path $target 'image-platform.txt'), "$platform`n", (New-Object Text.UTF8Encoding($false)))
Write-Host "Exported source-free package: $target"
Write-Host 'Give the folder and a separately secured .env to the recipient. No source, certificates, database, resumes or credentials were exported.'
Write-Host "Image platform: $platform. Recipient needs compatible Linux containers in Docker Desktop."
