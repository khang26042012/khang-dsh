const fs = require('fs');
(async () => {
  const out = { node: process.version, cwd: process.cwd(), time: new Date().toISOString() };
  try {
    const r = await fetch('https://api.github.com/zen', { headers: { 'User-Agent': 'probe' }, signal: AbortSignal.timeout(10000) });
    out.github = r.status;
  } catch (e) { out.github_err = String(e).slice(0, 60); }
  try {
    const r2 = await fetch('https://registry.npmjs.org/@deepseek-ai%2Fdsh', { headers: { 'User-Agent': 'probe' }, signal: AbortSignal.timeout(10000) });
    const j = await r2.json();
    out.npm_dsh_version = (j['dist-tags'] || {}).latest || Object.keys(j.versions || {})[0] || 'unknown';
  } catch (e) { out.npm_err = String(e).slice(0, 60); }
  const { execSync } = require('child_process');
  for (const cmd of ['python3 --version', 'git --version']) {
    try { out[cmd.split(' ')[0]] = execSync(cmd + ' 2>&1').toString().trim().slice(0, 30); }
    catch (e) { out[cmd.split(' ')[0] + '_err'] = 'missing'; }
  }
  fs.writeFileSync(process.cwd() + '/probe_result.json', JSON.stringify(out, null, 2));
  console.log('PROBE DONE', JSON.stringify(out));
})().catch(e => { console.error('PROBE FAIL', e); });
setTimeout(() => {}, 15000);
