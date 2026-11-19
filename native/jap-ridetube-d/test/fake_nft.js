#!/usr/bin/env node
'use strict';
// A stand-in for nft (test_ytd.js, WP9): the ip filter input chain kept in <state>.json, every call logged to
// <state>.log.   fake_nft.js <state> <nft args...>
// <state>.fail (a word): `list` fails with it (no unit firewall)
// <state>.busy (a number N): the next N `list` calls fail as a busy nft would (a rule may be there)
const fs = require('fs');
const state = process.argv[2], args = process.argv.slice(3);
const read = () => { try { return JSON.parse(fs.readFileSync(state + '.json', 'utf8')); } catch (e) { return { next: 10, rules: [] }; } };
const s = read();
fs.appendFileSync(state + '.log', args.join(' ') + '\n');
const save = () => fs.writeFileSync(state + '.json', JSON.stringify(s));
const j = args.join(' ');
if (j === '-a list chain ip filter input') {
    if (fs.existsSync(state + '.fail')) { process.stderr.write('Error: No such file or directory\n'); process.exit(1); }
    const busy = fs.existsSync(state + '.busy') ? Number(fs.readFileSync(state + '.busy', 'utf8')) : 0;
    if (busy > 0) { fs.writeFileSync(state + '.busy', String(busy - 1)); process.stderr.write('Error: Device or resource busy\n'); process.exit(1); }
    process.stdout.write('table ip filter {\n\tchain input { # handle 1\n\t\ttype filter hook input priority filter; policy drop;\n' +
        s.rules.map((r) => '\t\t' + r.text + ' # handle ' + r.h + '\n').join('') + '\t\tct state established accept # handle 2\n\t}\n}\n');
} else if (args.slice(0, 5).join(' ') === 'insert rule ip filter input') {
    s.rules.unshift({ h: s.next++, text: args.slice(5).join(' ') });
    save();
} else if (args.slice(0, 6).join(' ') === 'delete rule ip filter input handle') {
    const n = s.rules.length;
    s.rules = s.rules.filter((r) => String(r.h) !== args[6]);
    if (s.rules.length === n) { process.stderr.write('Error: Could not process rule: No such file or directory\n'); process.exit(1); }
    save();
} else {
    process.stderr.write('fake nft: ' + j + '\n');
    process.exit(1);
}
