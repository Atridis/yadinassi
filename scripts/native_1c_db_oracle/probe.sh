#!/usr/bin/env bash
# Read-only reviewed inputs; all native files remain in the private tmpfs.
set -euo pipefail
umask 077
exec 2>/dev/null
case "$#" in
  2) ;;
  3) case "$3" in
       --config-catalog-standard-binding|--config-catalog-name-binding|--config-catalog-reference-observation|--config-root-reference-projection-observation|--config-content-decode-observation|--config-blob-chain-observation|--config-entry-reference-observation|--config-zero-marker-filename-observation|--config-slot-marker-observation|--config-framing-observation|--config-transport-observation|--record-metadata-observation|--record-reader-validation|--params-transport-observation|--params-dbnames-extraction|--dbnames-identity-validation) ;;
       *) exit 2 ;;
     esac ;;
  *) exit 2 ;;
esac
[ "$1" = --invocation-nonce ] || exit 2
[[ "$2" =~ ^[0-9a-f]{32}$ ]] || exit 2
if [ "$#" -eq 3 ]; then
  exec python3 -B /oracle/run.py --invocation-nonce "$2" "$3"
fi
exec python3 -B /oracle/run.py --invocation-nonce "$2"
