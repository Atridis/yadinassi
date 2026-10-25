#!/usr/bin/env bash
# Read-only reviewed inputs; all native files remain in the private tmpfs.
set -euo pipefail
umask 077
exec 2>/dev/null
[ "$#" -eq 2 ] || { [ "$#" -eq 3 ] && [ "$3" = --record-metadata-observation ]; }
[ "$1" = --invocation-nonce ] && [[ "$2" =~ ^[0-9a-f]{32}$ ]]
if [ "$#" -eq 3 ]; then
  exec python3 -B /oracle/run.py --invocation-nonce "$2" --record-metadata-observation
fi
exec python3 -B /oracle/run.py --invocation-nonce "$2"
