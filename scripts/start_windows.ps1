# Start the FinAlly container. Pass -Build to force an image rebuild.
param([switch]$Build)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$Image = "finally"
$Container = "finally"
$Url = "http://localhost:8000"

docker image inspect $Image *> $null
if ($Build -or $LASTEXITCODE -ne 0) {
    docker build -t $Image .
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

if (-not (Test-Path ".env")) {
    Write-Host "No .env found; copy .env.example to .env and set OPENROUTER_API_KEY."
    exit 1
}

docker rm -f $Container *> $null
docker run -d --name $Container -v finally-data:/app/db -p 8000:8000 --env-file .env $Image | Out-Null
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "FinAlly is running at $Url"
Start-Process $Url
