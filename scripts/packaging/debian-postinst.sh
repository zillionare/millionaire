#!/bin/sh
set -eu
if ! getent passwd millionaire >/dev/null; then
    adduser --system --group --home /var/lib/millionaire millionaire
fi
install -d -m 0700 -o millionaire -g millionaire /var/lib/millionaire
/opt/millionaire/runtime/bin/python3.13 -m quantide.cli service install
systemctl start "${MILLIONAIRE_SERVICE_NAME:-millionaire}"
