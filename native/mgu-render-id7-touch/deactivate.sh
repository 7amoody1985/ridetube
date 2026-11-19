#!/bin/sh
# deactivate (before a removal, a rollback or a downgrade): the Store renderer's conf back to touch_area = auto, and the
# local conf's own line back where touch-guard.sh replaced it. No restart: the drop-ins are still in place now, so a
# renderer started here would get the area again; each takes the stock area at its next start. Already stock: nothing.
c=/var/opt/mgu-render/current/mgu-render.conf; l=/var/opt/mgu-render/mgu-render.local.conf
key='^[[:space:]]*touch_area[[:space:]]*='; mark='# mgu-render-id7-touch was: '
[ $# -gt 0 ] && { c=$1; l=$2; }
if [ -f "$c" ] && grep -q "${key}[[:space:]]*0,0,1920,720[[:space:]]*\$" "$c"; then sed -i "s/${key}.*\$/touch_area = auto/" "$c" || exit 1; fi
if [ -f "$l" ] && grep -q "^$mark" "$l"; then
    old=$(sed -n "s/^$mark//p" "$l" | tail -n 1)
    sed -i "/^$mark/d; /${key}[[:space:]]*0,0,1920,720[[:space:]]*\$/d" "$l" || exit 1
    printf '%s\n' "$old" >> "$l" || exit 1
fi
echo '{"status": "touch area back to the renderers'"'"' own at their next start"}'
