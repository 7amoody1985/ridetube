#!/bin/sh
# Runs before every mgu-render start (drop-in on mgu-render.service). iDrive 7: the idrive7-apps kit
# draws its header tabs in the title strip (y < 76), and "fill" screens (YouTube, Moonride, RideWatch)
# draw over the HMI's back column (x < 84); a renderer whose touch_area leaves either out hands those
# taps to the HMI, which closes the app. Apps that don't claim the column (every other layout) leave
# it to the HMI, so its back arrow still works there. An update replaces mgu-render.conf, so the value
# is put back here whatever version is installed, and in the local conf (read last) when it sets one;
# the local conf's own line is kept there as a comment for deactivate.sh to put back.
# Prints one line per file it changed (apply.sh restarts mgu-render only then).
# Usage: touch-guard.sh [conf...]   (default: the installed renderer's and the local conf)
area='0,0,1920,720'
key='^[[:space:]]*touch_area[[:space:]]*='
mark='# mgu-render-id7-touch was: '
[ $# -gt 0 ] || set -- /var/opt/mgu-render/current/mgu-render.conf /var/opt/mgu-render/mgu-render.local.conf
for f in "$@"; do
    [ -f "$f" ] || continue
    if grep -q "$key" "$f"; then
        [ "$(grep "$key" "$f" | sed 's/[[:space:]]//g' | sort -u)" = "touch_area=$area" ] && continue
        if [ "${f##*/}" != mgu-render.conf ]; then
            # the local conf: its key lines go, the last one kept as a comment (once), the area appended
            old=$(grep "$key" "$f" | tail -n 1)
            grep -q "^$mark" "$f" && old='' || old="$mark$old"
            sed -i "/$key/d" "$f" && { [ -z "$old" ] || printf '\n%s' "$old"; printf '\ntouch_area = %s\n' "$area"; } >> "$f" || { echo "touch-guard: $f not changed" >&2; continue; }
        else
            sed -i "s/$key.*\$/touch_area = $area/" "$f" || { echo "touch-guard: $f not changed" >&2; continue; }
        fi
    elif [ "${f##*/}" = mgu-render.conf ]; then
        printf '\ntouch_area = %s\n' "$area" >> "$f" || { echo "touch-guard: $f not changed" >&2; continue; }
    else
        continue
    fi
    echo "touch-guard: touch_area set to $area in $f"
done
exit 0
