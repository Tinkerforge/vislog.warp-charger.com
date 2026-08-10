#!/bin/sh
# Delete all protocols from the protocols/ directory that are older than 1 year
# (based on file modification time). Called by cron.sh.

set -e

PROTOCOL_DIR="$(dirname "$(readlink -f "$0")")/protocols"

if [ ! -d "$PROTOCOL_DIR" ]; then
    echo "Protocol directory $PROTOCOL_DIR not found, nothing to do."
    exit 0
fi

find "$PROTOCOL_DIR" -type f -mtime +365 -delete
