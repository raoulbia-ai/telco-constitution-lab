#!/usr/bin/env bash
# Track 1 NETCONF server entrypoint.
# Runs netopeer2-server in the foreground so Docker manages its lifecycle.
#   -d        : debug mode — do NOT daemonize, log to stderr (container-friendly)
#   -v <lvl>  : verbosity (0 error .. 2 debug)
set -euo pipefail

VERBOSITY="${NP2_VERBOSITY:-2}"

echo "[entrypoint] starting netopeer2-server (verbosity=${VERBOSITY}) on :830"
exec netopeer2-server -d -v "${VERBOSITY}"
