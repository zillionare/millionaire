#!/bin/sh
set -eu
launcher=$0
while [ -L "$launcher" ]; do
    parent=$(CDPATH= cd -- "$(dirname -- "$launcher")" && pwd)
    target=$(readlink "$launcher")
    case "$target" in
        /*) launcher=$target ;;
        *) launcher=$parent/$target ;;
    esac
done
runtime_root=$(CDPATH= cd -- "$(dirname -- "$launcher")" && pwd)
exec "$runtime_root/runtime/bin/python3.13" -m quantide.cli "$@"
