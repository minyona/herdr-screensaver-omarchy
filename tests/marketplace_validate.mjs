// The marketplace's own checks, run offline against this repo's committed HEAD:
//   node tests/marketplace_validate.mjs <omarchy-plugin-marketplace checkout> [repo dir]
// The checkout's scripts are imported unchanged (its package deps installed there, never here). Their GitHub
// reads go to a local fetch that answers from `git` in this repo, as https://github.com/minyona/herdr-screensaver-omarchy
// would at that commit (the planned public URL). Runs:
//   1. build-catalog.mjs inspectSubmission(url): root README + LICENSE, exactly one root manifest.json,
//      validateManifest(..., {community: true}), no symlinks, entry points exist, the preview decoded by sharp
//   2. security-baseline-scope.mjs resolveSecuritySnapshot (the marketplace's own file selection) and
//      security-baseline-analysis.mjs buildSecurityBaseline: expected outcome "passed", no findings, no capabilities
// Every URL the scripts asked for is printed, so it is plain that nothing left this machine.
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const [, , marketArg, repoArg] = process.argv;
if (!marketArg) {
  console.error('usage: node tests/marketplace_validate.mjs <omarchy-plugin-marketplace checkout> [repo dir]');
  process.exit(2);
}
const MARKET = path.resolve(marketArg);
const REPO = path.resolve(repoArg || path.join(path.dirname(fileURLToPath(import.meta.url)), '..'));
const OWNER = 'minyona', NAME = 'herdr-screensaver-omarchy';
const URL_ = `https://github.com/${OWNER}/${NAME}`;
const git = (args, opts = {}) => execFileSync('git', ['-C', REPO, ...args], { maxBuffer: 256 << 20, ...opts });
const HEAD = git(['rev-parse', 'HEAD']).toString().trim();
const TREE = git(['rev-parse', 'HEAD^{tree}']).toString().trim();
const marketSha = execFileSync('git', ['-C', MARKET, 'rev-parse', 'HEAD']).toString().trim();

// the tree as GitHub's API gives it: path, mode, type, sha, size
const tree = git(['ls-tree', '-r', '-t', '-l', 'HEAD']).toString().split('\n').filter(Boolean).map((line) => {
  const [meta, p] = line.split('\t');
  const [mode, type, sha, size] = meta.split(/\s+/);
  return type === 'blob' ? { path: p, mode, type, sha, size: Number(size) } : { path: p, mode, type, sha };
});
const byPath = new Map(tree.map((e) => [e.path, e]));

const asked = [];
const json = (obj) => new Response(JSON.stringify(obj), { status: 200, headers: { 'content-type': 'application/json' } });
async function localFetch(input, init = {}) {
  const url = new URL(typeof input === 'string' ? input : input.url);
  asked.push(url.href);
  const api = `/repos/${OWNER}/${NAME}`;
  if (url.hostname === 'api.github.com') {
    const p = url.pathname;
    if (p === api) return json({ full_name: `${OWNER}/${NAME}`, name: NAME, owner: { login: OWNER }, private: false, disabled: false, archived: false, fork: false, default_branch: 'main', description: 'Herdr Screensaver for Omarchy', html_url: URL_ });
    if (p === `${api}/commits/${HEAD}` || p === `${api}/commits/main` || p === `${api}/commits/HEAD`) return json({ sha: HEAD, commit: { tree: { sha: TREE } } });
    if (p === `${api}/branches/main`) return json({ name: 'main', commit: { sha: HEAD, commit: { tree: { sha: TREE } } } });
    if (p === `${api}/git/trees/${TREE}` || p === `${api}/git/trees/${HEAD}` || p === `${api}/git/trees/main`) return json({ sha: TREE, truncated: false, tree });
    if (p.startsWith(`${api}/contents/`)) {
      const rel = decodeURIComponent(p.slice(`${api}/contents/`.length));
      const e = byPath.get(rel);
      if (!e || e.type !== 'blob') return new Response('{"message":"Not Found"}', { status: 404 });
      const buf = git(['cat-file', 'blob', e.sha]);
      return json({ type: 'file', path: rel, sha: e.sha, size: e.size, encoding: 'base64', content: buf.toString('base64') });
    }
  }
  if (url.hostname === 'raw.githubusercontent.com') {
    const parts = url.pathname.split('/').slice(1);   // owner, repo, ref, ...path
    if (parts[0] === OWNER && parts[1] === NAME && [HEAD, 'main', 'HEAD'].includes(parts[2])) {
      const rel = parts.slice(3).map(decodeURIComponent).join('/');
      const e = byPath.get(rel);
      if (!e || e.type !== 'blob') return new Response('404: Not Found', { status: 404 });
      let buf = git(['cat-file', 'blob', e.sha]);
      const range = (init.headers && (init.headers.Range || init.headers.range || (init.headers.get && init.headers.get('range')))) || '';
      const m = /bytes=(\d+)-(\d+)/.exec(range);
      if (m) {
        buf = buf.subarray(Number(m[1]), Number(m[2]) + 1);
        return new Response(buf, { status: 206, headers: { 'content-length': String(buf.length) } });
      }
      return new Response(buf, { status: 200, headers: { 'content-length': String(buf.length) } });
    }
  }
  return new Response(`{"message":"not served offline: ${url.href}"}`, { status: 404 });
}
globalThis.fetch = localFetch;   // inspectSubmission reads through the global fetch
delete process.env.GITHUB_TOKEN;

let fail = 0;
const ok = (m) => console.log('ok   ' + m);
const bad = (m) => { console.log('FAIL ' + m); fail++; };
console.log(`marketplace checkout ${MARKET} at ${marketSha}; repo ${REPO} at ${HEAD} served as ${URL_}`);

const catalog = await import(pathToFileURL(path.join(MARKET, 'scripts/build-catalog.mjs')).href);
try {
  const r = await catalog.inspectSubmission(URL_);
  const m = r.manifests;
  if (m.length === 1 && m[0].id === 'io.github.minyona.herdr-screensaver' && m[0].path === 'manifest.json' && r.preview === true && r.commitSha === HEAD) {
    ok(`1. inspectSubmission: ${JSON.stringify({ repository: r.repository, commitSha: r.commitSha, license: r.license, preview: r.preview, manifests: m })}`);
  } else bad(`1. inspectSubmission returned ${JSON.stringify(r)}`);
} catch (e) {
  bad(`1. inspectSubmission threw ${e.code || ''}: ${e.message}`);
}
// validateManifest directly, community mode, on the committed manifest
try {
  const man = JSON.parse(git(['show', 'HEAD:manifest.json']).toString());
  catalog.validateManifest(man, 'manifest.json', { community: true });
  ok(`1. validateManifest(manifest, "manifest.json", {community: true}): no error (version ${man.version}, ${man.version.length} <= ${catalog.maximumManifestVersionLength} chars)`);
} catch (e) {
  bad(`1. validateManifest threw ${e.code || ''}: ${e.message}`);
}

const scope = await import(pathToFileURL(path.join(MARKET, 'scripts/security-baseline-scope.mjs')).href);
const analysis = await import(pathToFileURL(path.join(MARKET, 'scripts/security-baseline-analysis.mjs')).href);
try {
  const snap = await scope.resolveSecuritySnapshot(URL_, HEAD, { fetchImpl: localFetch, token: '' });
  const files = snap.files || snap;
  const scanned = files.map((f) => f.path).sort();
  console.log(`     scanned by the marketplace's selection (${scanned.length}): ${scanned.join(', ')}`);
  const own = git(['ls-files']).toString().split('\n').filter(Boolean).filter((p) => scope.isSecurityScanPath(p));
  console.log(`     isSecurityScanPath alone (${own.length}): ${own.join(', ')}`);
  const report = analysis.buildSecurityBaseline({ repository: `${OWNER}/${NAME}`, repoUrl: URL_, commitSha: HEAD, files }, { checkedAt: '2026-10-18T00:00:00.000Z' });
  const summary = { outcome: report.outcome, disposition: report.disposition, blocksApproval: report.blocksApproval, findings: report.findings, capabilities: report.capabilities };
  if (report.outcome === 'passed' && report.findings.length === 0 && report.capabilities.length === 0) ok(`2. security baseline: ${JSON.stringify(summary)}`);
  else bad(`2. security baseline: ${JSON.stringify(summary, null, 1)}`);
} catch (e) {
  bad(`2. security baseline threw ${e.code || ''}: ${e.message}`);
}

const hosts = [...new Set(asked.map((u) => new URL(u).hostname))];
console.log(`     ${asked.length} requests, all answered locally from git (hosts named: ${hosts.join(', ')}); not served: ${asked.filter((u) => !/api\.github\.com\/repos\/minyona\/herdr-screensaver-omarchy|raw\.githubusercontent\.com\/minyona\/herdr-screensaver-omarchy/.test(u)).join(', ') || 'none'}`);
console.log(`marketplace_validate: ${fail ? `FAILED (${fail})` : 'PASS'}`);
process.exit(fail ? 1 : 0);
