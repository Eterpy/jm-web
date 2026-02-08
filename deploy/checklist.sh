#!/usr/bin/env sh
set -eu

echo "[1] docker version"
docker --version
docker compose version

echo "[2] compose config"
docker compose config >/dev/null

echo "[3] services"
docker compose ps
