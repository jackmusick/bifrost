#!/bin/bash
# Bifrost Development Launcher
# Ensure node_modules dir exists for Docker anonymous volume mountpoint
# (gitignored, so missing after fresh clone; needed because ./api/src is mounted :ro)
mkdir -p api/src/services/app_compiler/node_modules

docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build