#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose down
docker compose up -d --force-recreate
docker compose logs -f energia-png-generator
