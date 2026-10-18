// node --test tests/model.test.mjs: the decisions and exact argv Service.qml takes from Model.js.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// Model.js is a QML JS file (no extension type); load it as CommonJS through a .cjs copy
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'herdr-model-'));
fs.copyFileSync(path.join(ROOT, 'Model.js'), path.join(tmp, 'Model.cjs'));
const M = createRequire(import.meta.url)(path.join(tmp, 'Model.cjs'));

test('leadTimeout: 2 s before the screensaver, never armed without one', () => {
  assert.equal(M.leadTimeout(150, 300), 148);
  assert.equal(M.leadTimeout(0, 300), 0);
  assert.equal(M.leadTimeout(-1, 300), 0);
  assert.equal(M.leadTimeout(2, 300), 1);
  assert.equal(M.leadTimeout(3, 300), 1);
  assert.equal(M.leadTimeout(300, 300), 0, 'lock together with the screensaver: Omarchy shows none');
  assert.equal(M.leadTimeout(300, 150), 0, 'lock first: Omarchy shows none');
  assert.equal(M.leadTimeout(NaN, 300), 0);
});

test('secondsFromConfig is Omarchy IdleModel.secondsFromConfig', () => {
  const src = fs.readFileSync(path.join(ROOT, 'tests/omarchy/fixtures/v4-real/shell/plugins/services/idle/IdleModel.js'), 'utf8');
  fs.writeFileSync(path.join(tmp, 'IdleModel.cjs'), src);
  const I = createRequire(import.meta.url)(path.join(tmp, 'IdleModel.cjs'));
  for (const v of [undefined, null, '', '90', 90.7, -5, 'x', 0, Infinity]) {
    assert.equal(M.secondsFromConfig(v, 150), I.secondsFromConfig(v, 150), String(v));
  }
});

test('shouldArm: only enabled + takeover + stay-awake known off', () => {
  const on = { enabled: true, takeover: true, stayAwake: false, stayAwakeLoaded: true };
  assert.equal(M.shouldArm(on), true);
  assert.equal(M.shouldArm({ ...on, takeover: false }), false);
  assert.equal(M.shouldArm({ ...on, enabled: false }), false);
  assert.equal(M.shouldArm({ ...on, stayAwake: true }), false);
  assert.equal(M.shouldArm({ ...on, stayAwakeLoaded: false }), false);
  assert.equal(M.shouldArm(null), false);
});

test('parseState: defaults, first line wins, bad values ignored', () => {
  assert.deepEqual(M.parseState(''), { enabled: 'on', takeover: 'off', takeover_since: '', lock_on_wake: 'on', font_size: 'auto' });
  const s = M.parseState('takeover=on\ntakeover=off\nfont_size=9.5\nlock_on_wake=maybe\nbogus=1\nenabled=off\ntakeover_since=2026-10-18T00:00:00Z\n');
  assert.deepEqual(s, { enabled: 'off', takeover: 'on', takeover_since: '2026-10-18T00:00:00Z', lock_on_wake: 'on', font_size: '9.5' });
  assert.equal(M.parseState('font_size=37').font_size, 'auto');
  assert.equal(M.parseState('font_size=36').font_size, '36');
  assert.equal(M.parseState('font_size=5').font_size, 'auto');
});

test('validFontSize matches ctl and font-size.sh', () => {
  for (const v of ['auto', '6', '9', '9.5', '35.5', '36']) assert.ok(M.validFontSize(v), v);
  for (const v of ['5.5', '36.5', '37', '12.3', '', 'x', '-9', ' 9', '08', '010']) assert.ok(!M.validFontSize(v), v);
});

test('launchArgv carries the marker; paths stay arguments (HOME with spaces)', () => {
  const dir = 'file:///home/a b/.config/omarchy/plugins/io.github.minyona.herdr-screensaver/';
  const idle = M.launchArgv(dir, 'idle');
  assert.deepEqual(idle.slice(0, 2), ['bash', '-lc']);
  assert.equal(idle[3], '/home/a b/.config/omarchy/plugins/io.github.minyona.herdr-screensaver/bin/herdr-screensaver-launch');
  assert.deepEqual(idle.slice(4), ['idle', 'org.omarchy.screensaver']);
  assert.ok(!idle[2].includes('/home'), 'no path in the script text');
  assert.match(idle[2], /omarchy-shell lock isLocked/);
  const force = M.launchArgv(dir, 'force');
  assert.deepEqual(force.slice(4), ['force', 'org.omarchy.screensaver']);
  assert.ok(!force[2].includes('isLocked'));
  assert.equal(M.launchArgv(dir, 'anything')[4], 'idle');
  // the marker matches Omarchy's own gate pattern
  assert.match(idle.join(' '), /[o]rg.omarchy.screensaver/);
  assert.equal(M.dirFromUrl('file:///home/a%20b/x'), '/home/a b/x/');
});

test('ctlArgv and the scripts it runs: bash -lc with "$0" "$@" really keeps a spaced path whole', () => {
  const argv = M.ctlArgv('file:///p q/', 'set', 'takeover', 'on');
  assert.deepEqual(argv, ['bash', '-lc', 'exec bash "$0" "$@"', '/p q/bin/herdr-screensaver-ctl', 'set', 'takeover', 'on']);
  // run the exact script text with a stand-in for the path: it gets every argument whole
  const d = fs.mkdtempSync(path.join(tmp, 'a b '));
  const f = path.join(d, 'echo args');
  fs.writeFileSync(f, 'printf "%s|" "$0" "$@"\n');
  const out = execFileSync('bash', ['-c', argv[2], f, 'set', 'x y'], { encoding: 'utf8' });
  assert.equal(out, `${f}|set|x y|`);
});

test('statusText: one ON/OFF line per piece', () => {
  const t = M.statusText({
    state: M.parseState('takeover=on\ntakeover_since=T\n'), armed: true, timeout: 148, screensaver: 150,
    stayAwake: false, stayAwakeLoaded: true, probes: 'enabled: ON\nshowing: OFF\npython3: ON (3.12)\nterminal: ON (Alacritty.desktop)\nold one-liner install: none\n'
  });
  assert.equal(t, [
    'enabled: ON', 'takeover: ON (since T)', 'lock on wake: ON', 'font size: auto',
    "idle monitor: ARMED (148 s, 2 s before Omarchy's screensaver at 150 s)", 'stay-awake: OFF',
    'showing: OFF', 'python3: ON (3.12)', 'terminal: ON (Alacritty.desktop)', 'old one-liner install: none'
  ].join('\n'));
  assert.match(M.statusText({}), /idle monitor: OFF/);
  assert.match(M.statusText({}), /probes: not run yet/);
});
