#!/bin/sh
set -eu

script_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
requested_scope=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --system) requested_scope=system; shift ;;
        *) printf '%s\n' "Unknown argument: $1" >&2; exit 2 ;;
    esac
done

# The archive and the installed copy both expose this command.  Only the
# managed destination contains the ownership marker and service metadata.
if [ -n "${MILLIONAIRE_INSTALL_ROOT:-}" ]; then
    install_root=$MILLIONAIRE_INSTALL_ROOT
elif [ "$requested_scope" = system ]; then
    install_root=/usr/local/share/millionaire
elif [ -f "$script_root/.millionaire-install" ]; then
    install_root=$script_root
else
    install_root=$HOME/.local/share/millionaire
fi
if [ ! -d "$install_root" ]; then
    printf '%s\n' "No managed Millionaire installation found at: $install_root" \
        'For a custom location, set MILLIONAIRE_INSTALL_ROOT. For a system install, use --system.' >&2
    exit 1
fi
install_root=$(CDPATH= cd -- "$install_root" && pwd)
if [ "$install_root" = / ] || [ "$install_root" = "$HOME" ] || \
    [ ! -f "$install_root/.millionaire-install" ] || \
    [ "$(cat "$install_root/.millionaire-install")" != 'Millionaire managed installation' ] || \
    [ ! -f "$install_root/service-scope" ] || [ ! -f "$install_root/bin-dir" ] || \
    [ ! -x "$install_root/current/millionaire" ]; then
    printf '%s\n' "Refusing to remove an unrecognized installation: $install_root" \
        'Use the installed uninstall.sh path printed by install.sh, or set MILLIONAIRE_INSTALL_ROOT.' >&2
    exit 1
fi
scope=$(cat "$install_root/service-scope")
case "$scope" in
    user|system) ;;
    *) printf '%s\n' 'Invalid installation service scope; nothing was removed.' >&2; exit 1 ;;
esac
if [ -n "$requested_scope" ] && [ "$requested_scope" != "$scope" ]; then
    printf '%s\n' 'The requested scope does not match this installation; nothing was removed.' >&2
    exit 1
fi
bin_dir=$(cat "$install_root/bin-dir")
[ -n "$bin_dir" ] || { printf '%s\n' 'Missing CLI directory; nothing was removed.' >&2; exit 1; }
printf '%s\n' "Uninstalling Millionaire from: $install_root"
set --
if [ "$scope" = system ]; then set -- --system; fi
"$install_root/current/millionaire" control --uninstall "$@"
"$install_root/current/millionaire" service uninstall "$@"
if [ -L "$bin_dir/millionaire" ] && \
    [ "$(readlink "$bin_dir/millionaire")" = "$install_root/current/millionaire" ]; then
    rm "$bin_dir/millionaire"
fi
rm -rf "$install_root"
printf '%s\n' 'Millionaire removed. User settings, extensions and data were retained.'
