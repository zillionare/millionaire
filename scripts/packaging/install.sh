#!/bin/sh
set -eu

archive_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
scope=user
service_user=
while [ "$#" -gt 0 ]; do
    case "$1" in
        --system) scope=system; shift ;;
        --user) service_user=${2:?--user requires an account}; shift 2 ;;
        *) printf '%s\n' "Unknown argument: $1" >&2; exit 2 ;;
    esac
done
if [ "$scope" = system ]; then
    [ "$(id -u)" = 0 ] || { printf '%s\n' 'System installation requires sudo.' >&2; exit 1; }
    [ -n "$service_user" ] && [ "$service_user" != root ] || {
        printf '%s\n' 'Use --system --user <non-root-account>.' >&2; exit 2;
    }
    install_root=${MILLIONAIRE_INSTALL_ROOT:-/usr/local/share/millionaire}
    bin_dir=${MILLIONAIRE_BIN_DIR:-/usr/local/bin}
    set -- --system --user "$service_user"
else
    install_root=${MILLIONAIRE_INSTALL_ROOT:-"$HOME/.local/share/millionaire"}
    bin_dir=${MILLIONAIRE_BIN_DIR:-"$HOME/.local/bin"}
    # Native services explicitly choose durable data; source runs default to tmp.
    export QUANTIDE_DATA_HOME="${QUANTIDE_DATA_HOME:-$HOME/.quantide}"
    set --
fi
mkdir -p "$install_root/versions" "$bin_dir"
if [ -e "$install_root/current" ] && [ ! -f "$install_root/.millionaire-install" ]; then
    printf '%s\n' 'The destination is not a managed Millionaire installation.' >&2
    exit 1
fi
previous=
if [ -L "$install_root/current" ]; then previous=$(readlink "$install_root/current"); fi
version=$(cat "$archive_root/VERSION")
destination=$(mktemp -d "$install_root/versions/$version.XXXXXX")
cp -R "$archive_root/runtime" "$archive_root/millionaire" "$destination/"
if [ -d "$archive_root/Millionaire.app" ]; then
    cp -R "$archive_root/Millionaire.app" "$destination/"
fi
if [ "$scope" = system ]; then chmod 755 "$install_root" "$install_root/versions" "$destination"; fi
committed=false
rollback() {
    result=$?
    trap - 0
    if [ "$committed" != true ]; then
        if [ "$scope" = system ]; then
            "$destination/millionaire" control --uninstall --system >/dev/null 2>&1 || true
        else
            "$destination/millionaire" control --uninstall >/dev/null 2>&1 || true
        fi
        "$destination/millionaire" service uninstall "$@" >/dev/null 2>&1 || true
        if [ -n "$previous" ]; then
            rm -f "$install_root/current"
            ln -s "$previous" "$install_root/current"
            "$previous/millionaire" service install "$@" || true
            "$previous/millionaire" service start "$@" || true
            if [ "$scope" = system ]; then
                "$previous/millionaire" control --install --system >/dev/null 2>&1 || true
            else
                "$previous/millionaire" control --install >/dev/null 2>&1 || true
            fi
        else
            rm -f "$install_root/current"
        fi
        rm -rf "$destination"
        printf '%s\n' 'Installation failed; the previous installation was restored.' >&2
    fi
    exit "$result"
}
trap 'rollback "$@"' 0
if [ -n "$previous" ]; then "$previous/millionaire" service stop "$@"; fi
ln -s "$destination" "$install_root/current.new.$$"
"$destination/runtime/bin/python3.13" -c \
    'import os,sys; os.replace(sys.argv[1], sys.argv[2])' \
    "$install_root/current.new.$$" "$install_root/current"
"$install_root/current/millionaire" service install "$@"
"$install_root/current/millionaire" service start "$@"
"$destination/runtime/bin/python3.13" "$archive_root/wait-for-service.py"
if [ "$scope" = system ]; then
    "$destination/millionaire" control --install --system
else
    "$destination/millionaire" control --install
fi
cp "$archive_root/uninstall.sh" "$install_root/uninstall.sh"
chmod 755 "$install_root/uninstall.sh"
printf '%s\n' "$scope" > "$install_root/service-scope"
printf '%s\n' "$bin_dir" > "$install_root/bin-dir"
printf '%s\n' 'Millionaire managed installation' > "$install_root/.millionaire-install"
ln -sf "$install_root/current/millionaire" "$bin_dir/millionaire"
committed=true
printf '%s\n' "Installed. Control: $bin_dir/millionaire control" \
    "Uninstall (retains data): sh $install_root/uninstall.sh"
