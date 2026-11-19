#!/bin/sh
# Node 8 gate for the code the car runs on its system Node 8: the daemon (ytd.js under /usr/bin/node, its --fetch child
# too, and any daemon file beside it: gen.js ships there as oapgen.js) and the app with the kit runtime build.py ships (MainApp's Node). thumb.js and vendor/jpeg-js run on jap-node22: not here.
# `node --check` in the node:8 image catches syntax (?. ?? catch {} ...); a grep catches the newer calls it cannot see.
#   tools/check_node8.sh               from anywhere; exit 1 on any finding, or when Docker or the image is missing
#   tools/check_node8.sh --self-test   proves the gate fails on each kind of finding
set -eu
self=$(cd "$(dirname "$0")" && pwd)/$(basename "$0")
cd "$(dirname "$self")/.."
IMAGE=${NODE8_IMAGE:-node:8-alpine}
FILES=${NODE8_FILES:-$(ls native/jap-ridetube-d/*.js kit/tools/oapgen/gen.js apps/jap_ridetube/*.js kit/runtime/*.js | grep -v '^native/jap-ridetube-d/thumb\.js$')}
NEWER='\.rmSync\(|\.replaceAll\(|\.matchAll\(|\.flatMap\(|\.flat\(|Object\.fromEntries|Promise\.allSettled|globalThis|\(\?<[=!]'

if [ "${1:-}" = --self-test ]; then
    t=$(mktemp -d "$PWD/.node8-XXXXXX"); trap 'rm -rf "$t"' EXIT
    printf 'a?.b;\n' > "$t/optional_chaining.js"; printf 'a ?? b;\n' > "$t/nullish.js"
    printf 'try { f(); } catch { }\n' > "$t/catch_binding.js"; printf 'fs.rmSync(p);\n' > "$t/rmsync.js"
    printf "s.replaceAll('a', 'b');\n" > "$t/replaceall.js"; printf '/(?<=x)y/.test(s);\n' > "$t/lookbehind.js"
    printf 'const ok = [1].map((x) => x * 2);\n' > "$t/fine.js"
    for f in "$t"/*.js; do
        b=${f#$PWD/}
        if NODE8_FILES=$b sh "$self" >/dev/null 2>&1; then r=pass; else r=fail; fi
        case "$(basename "$f"):$r" in fine.js:pass | *.js:fail) echo "ok   $(basename "$f") $r" ;; *) echo "FAIL $(basename "$f") $r"; exit 1 ;; esac
    done
    exit 0
fi

command -v docker >/dev/null 2>&1 || { echo "check_node8: docker not found" >&2; exit 1; }
n=$(echo "$FILES" | wc -w | tr -d ' ')
rc=0
if found=$(grep -nE "$NEWER" $FILES); then echo "check_node8: not in Node 8:" >&2; echo "$found" >&2; rc=1; fi
# every file checked inside the container, or it fails (an empty bind mount must not pass)
out=$(docker run --rm --network none -v "$PWD:/src:ro" -w /src "$IMAGE" sh -c \
    'n=0; rc=0; for f; do node --check "$f" || rc=1; n=$((n+1)); done; echo "checked $n on $(node --version)"; exit $rc' sh $FILES) || rc=1
echo "$out"
case "$out" in *"checked $n on v8."*) ;; *) echo "check_node8: expected $n files checked on Node 8" >&2; rc=1 ;; esac
[ $rc = 0 ] && echo "check_node8: $n files ok"
exit $rc
