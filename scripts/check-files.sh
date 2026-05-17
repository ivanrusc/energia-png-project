#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source .env
watch -n 10 "date; stat -c '%y  %s  %n' public/${PUBLIC_SLUG}/energia*.png"
