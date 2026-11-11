# Build (if needed) and run the FinAlly container. Pass -Build to force a rebuild.
param([switch]$Build)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$Image = "finally"
$Container = "finally"

if (-not (Test-Path ".env")) {
    Write-Host "No .env found; copying .env.example. Add your OPENROUTER_API_KEY to .env."
    Copy-Item ".env.example" ".env"
}

docker image inspect $Image *> $null
if ($Build -or $LASTEXITCODE -ne 0) {
    docker build -t $Image .
}

docker rm -f $Container *> $null
docker run -d --name $Container -v finally-data:/app/db -p 8000:8000 --env-file .env $Image | Out-Null

Write-Host "FinAlly is running at http://localhost:8000"
Start-Process "http://localhost:8000"
