#!/usr/bin/env bash
# Build (if needed) and run the FinAlly container. Pass --build to force a rebuild.
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE=finally
CONTAINER=finally

if [[ ! -f .env ]]; then
  echo "No .env found; copying .env.example. Add your OPENROUTER_API_KEY to .env."
  cp .env.example .env
fi

if [[ "${1:-}" == "--build" ]] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker build -t "$IMAGE" .
fi

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$CONTAINER" -v finally-data:/app/db -p 8000:8000 --env-file .env "$IMAGE" >/dev/null

echo "FinAlly is running at http://localhost:8000"
if command -v open >/dev/null 2>&1; then
  open http://localhost:8000
fi
