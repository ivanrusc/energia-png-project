#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .env
URL="https://${PUBLIC_DOMAIN}/${PUBLIC_SLUG}/${FILE_NAME_MAIN}"
echo "URL: $URL"
echo
curl -I "$URL"
