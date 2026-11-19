#!/bin/sh
# idrive7-renderd (the idrive7-apps kit's renderer) as its own unit file starts it, with touch_area added: the whole
# screen is the apps' to claim, so a full-screen app ("fill") gets taps on the HMI's back column too. Apps claim only
# what they draw, so the others still leave that column to the HMI. The command is read from the unit file at each
# start (an update that changes it is followed); when it cannot be read, or holds anything a plain word split would
# change (quotes, $, %, globs, a continued line), the command of idrive7-renderd 2.1.19, said on stderr.
# Usage: renderd-touch.sh [unit file]   (default: the unit's FragmentPath)
set -f
AREA=0,0,1920,720
B='/var/opt/idrive7-renderd/current/mgu-renderd -s socket_path=/run/mgu-renderd/renderd.sock -s socket_group=tm_oap_app -s embed_marker=/run/mgu-renderd-hmi/hmi-template'
f=${1:-$(systemctl show -p FragmentPath --value idrive7-renderd.service 2>/dev/null)}
cmd=$(sed -n 's/^ExecStart[[:space:]]*=[[:space:]]*[-@+!:]*//p' "${f:-/etc/systemd/system/idrive7-renderd.service}" 2>/dev/null | grep 'mgu-renderd' | tail -n 1)
case "$cmd" in *[!A-Za-z0-9\ _./=:,@+-]*) cmd= ;; esac
case "$cmd" in
    /var/opt/idrive7-renderd/*mgu-renderd*) ;;
    *) echo "renderd-touch: the unit's command (${f:-no unit file}) not used, idrive7-renderd 2.1.19's instead" >&2; cmd=$B ;;
esac
[ -n "$DRY_RUN" ] && { echo $cmd -s touch_area=$AREA; exit 0; }
exec $cmd -s touch_area=$AREA
