#!/bin/sh
# Self-check of touch-guard.sh and renderd-touch.sh (BusyBox sh/sed, as on the car): docker run --rm -v $PWD:/w busybox sh /w/test.sh
g=/w/touch-guard.sh; d=/tmp/r; mkdir -p $d; t=$d/mgu-render.conf; l=$d/mgu-render.local.conf; fail=0
check() { if grep -q '^touch_area = 0,0,1920,720$' $1 && [ "$(grep -c '^touch_area' $1)" = 1 ]; then echo "ok   $2"; else echo "FAIL $2"; cat $1; fail=1; fi; }
printf 'a = 1\ntouch_area = auto\nb = 2\n' > $t; sh $g $t >/dev/null; check $t "auto replaced"
printf 'touch_area = 84,0,1836,720\n' > $t; sh $g $t >/dev/null; check $t "old value replaced"
printf 'touch_area = 0,0,1920,720\n' > $t; cp $t $t.0; sh $g $t; cmp -s $t $t.0 && echo "ok   already right: file untouched" || { echo "FAIL rewritten"; fail=1; }
printf 'a = 1\n' > $t; sh $g $t >/dev/null; check $t "missing key appended"; grep -q '^a = 1$' $t || { echo "FAIL other keys lost"; fail=1; }
printf 'x = 1\ntouch_area = 84,0,1836,720\n' > $l; printf 'a = 1\n' > $t; sh $g $t $l >/dev/null; check $l "local conf replaced"; check $t "both files"
printf 'x = 1\n' > $l; sh $g $l >/dev/null; grep -q touch_area $l && { echo "FAIL key added to local conf"; fail=1; } || echo "ok   local conf without key left alone"
sh $g /tmp/none && echo "ok   missing file: exit 0" || { echo "FAIL missing file"; fail=1; }
# renderd-touch.sh: the unit's own command, touch_area added
r=/w/renderd-touch.sh; u=$d/idrive7-renderd.service; A='-s touch_area=0,0,1920,720'
B='/var/opt/idrive7-renderd/current/mgu-renderd -s socket_path=/run/mgu-renderd/renderd.sock -s socket_group=tm_oap_app -s embed_marker=/run/mgu-renderd-hmi/hmi-template'
want() { got=$(DRY_RUN=1 sh $r $1); [ "$got" = "$2" ] && echo "ok   $3" || { echo "FAIL $3: $got"; fail=1; }; }
printf '[Service]\nExecStartPre=/bin/sh -c true\nExecStart=%s\nRestart=always\n' "$B" > $u; want $u "$B $A" "unit command + touch_area"
printf '[Service]\nExecStart=%s -s new_key=1\n' "$B" > $u; want $u "$B -s new_key=1 $A" "a changed command is followed"
want $d/none.service "$B $A" "no unit file: the 2.1.19 command"
printf '[Service]\nExecStart=/usr/bin/other --x\n' > $u; want $u "$B $A" "another program: the 2.1.19 command"
printf '[Service]\nExecStart=-%s\n' "$B" > $u; want $u "$B $A" "an ExecStart= prefix (-) is stripped, the unit's command kept"
printf '[Service]\nExecStart = %s -s x=2\n' "$B" > $u; want $u "$B -s x=2 $A" "ExecStart = (spaces)"
printf '[Service]\nExecStart=%s -s "foreground_gate=/usr/bin/node /x/g.js"\n' "$B" > $u; want $u "$B $A" "quotes: not split by hand, the 2.1.19 command"
printf '[Service]\nExecStart=%s -s p=%%t/x\n' "$B" > $u; want $u "$B $A" "a systemd specifier: the 2.1.19 command"
printf '[Service]\nExecStart=%s -s g=*\n' "$B" > $u; want $u "$B $A" "a glob: the 2.1.19 command"
DRY_RUN=1 sh $r $d/none.service 2>&1 >/dev/null | grep -q '2.1.19' && echo "ok   the fallback is said on stderr" || { echo "FAIL fallback silent"; fail=1; }
# touch-guard: spacing, a conf without a final newline, the local conf's own line kept for deactivate
printf 'a = 1\n\ttouch_area\t= 84,0,1836,720\n' > $t; sh $g $t >/dev/null; check $t "an indented key (tab) replaced"
printf 'a = 1' > $t; sh $g $t >/dev/null; check $t "no final newline: key appended on its own line"; grep -q '^a = 1$' $t || { echo "FAIL last key corrupted"; fail=1; }
printf 'x = 1\ntouch_area = 84,0,1836,720\n' > $l; printf 'touch_area = auto\n' > $t; [ -n "$(sh $g $t $l)" ] && echo "ok   a change is printed" || { echo "FAIL change not printed"; fail=1; }
check $l "local conf (again)"; grep -q '^# mgu-render-id7-touch was: touch_area = 84,0,1836,720$' $l && echo "ok   the local conf's own line kept as a comment" || { echo "FAIL old line not kept"; cat $l; fail=1; }
[ -z "$(sh $g $t $l)" ] && echo "ok   nothing to change: nothing printed" || { echo "FAIL printed without a change"; fail=1; }
sh /w/deactivate.sh $t $l >/dev/null; grep -q '^touch_area = auto$' $t && echo "ok   deactivate: the conf back to auto" || { echo "FAIL deactivate conf"; cat $t; fail=1; }
[ "$(grep -c touch_area $l)" = 1 ] && grep -q '^touch_area = 84,0,1836,720$' $l && ! grep -q 'id7-touch' $l && echo "ok   deactivate: the local conf's own line back" || { echo "FAIL deactivate local"; cat $l; fail=1; }
cp $t $t.0; cp $l $l.0; sh /w/deactivate.sh $t $l >/dev/null; cmp -s $t $t.0 && cmp -s $l $l.0 && echo "ok   deactivate when stock: nothing changed" || { echo "FAIL deactivate not idempotent"; fail=1; }
# the drop-in's inline command, as systemd runs it ($$ is $): the script when there, else 2.1.19's command
x=$(sed -n "s/^ExecStart=\/bin\/sh -c '\(.*\)'\$/\1/p" /w/dropins/idrive7-renderd.service.d/mgu-render-id7-touch.conf | sed 's/\$\$/$/g')
got=$(sh -c "$(echo "$x" | sed 's|exec /bin/sh|echo script|; s|exec /var|echo /var|')"); [ "$got" = "echo $B" ] || [ "$got" = "$B" ] && echo "ok   drop-in: no script, 2.1.19's command" || { echo "FAIL drop-in fallback: $got"; fail=1; }
for f in apply.sh deactivate.sh; do sh -n /w/$f && echo "ok   $f parses" || { echo "FAIL $f syntax"; fail=1; }; done
exit $fail
