#!/bin/sh
# activate: a renderer that runs now without the touch area starts again with it (drop-ins and conf are read at a
# start); one that has it already, or does not run, is left alone, so a reinstall restarts nothing. Fails (the
# install rolls back) when one it restarted is not running with the area 10 s later, or restarted on its own meanwhile.
A=0,0,1920,720
d=$(dirname "$0")
has() { p=$(systemctl show -p MainPID --value "$1" 2>/dev/null); [ -n "$p" ] && [ "$p" != 0 ] && tr '\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q "touch_area=$A"; }
active() { [ "$(systemctl is-active "$1" 2>/dev/null)" = active ]; }
systemctl daemon-reload
todo=''
if active mgu-render.service; then
    # its area comes from the conf: restart only when touch-guard.sh had to change it
    [ -n "$(sh "$d/touch-guard.sh")" ] && todo="$todo mgu-render.service"
fi
if active idrive7-renderd.service && ! has idrive7-renderd.service; then todo="$todo idrive7-renderd.service"; fi
[ -z "$todo" ] && { echo "{\"status\": \"touch area $A: nothing to restart\"}"; exit 0; }
n0=''; for u in $todo; do n0="$n0 $(systemctl show -p NRestarts --value $u)"; done
systemctl try-restart $todo
sleep 10
set -- $n0
for u in $todo; do
    active $u || { echo "$u is not running after its restart" >&2; exit 1; }
    [ "$(systemctl show -p NRestarts --value $u)" = "$1" ] || { echo "$u restarted on its own after its restart" >&2; exit 1; }
    shift
done
case "$todo" in *idrive7-renderd*) has idrive7-renderd.service || { echo "idrive7-renderd runs without touch_area=$A" >&2; exit 1; } ;; esac
echo "{\"status\": \"touch area $A:$todo restarted\"}"
