#!/bin/bash
set -e

# Bifrost Development Launcher
# Ensure node_modules dir exists for Docker anonymous volume mountpoint
# (gitignored, so missing after fresh clone; needed because ./api/src is mounted :ro)

BIFROST_VERSION=$(git describe --tags --always --dirty 2>/dev/null || echo "unknown")
export BIFROST_VERSION
export VITE_BIFROST_VERSION="$BIFROST_VERSION"

mkdir -p api/src/services/app_compiler/node_modules

docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build