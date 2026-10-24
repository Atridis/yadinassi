#!/usr/bin/env bash
# Read-only reviewed inputs; all native files remain in the private tmpfs.
set -euo pipefail
umask 077
exec 2>/dev/null
[ "$#" -eq 2 ] && [ "$1" = --invocation-nonce ] && [[ "$2" =~ ^[0-9a-f]{32}$ ]]
exec python3 -B /oracle/run.py --invocation-nonce "$2"
