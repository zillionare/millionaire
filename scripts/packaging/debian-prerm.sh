#!/bin/sh
set -eu
if [ "$1" = remove ] || [ "$1" = upgrade ]; then
    systemctl stop "${MILLIONAIRE_SERVICE_NAME:-millionaire}"
fi
