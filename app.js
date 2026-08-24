// APP WORKER v3 - diag + giu cho
const { execSync } = require('child_process');
const fs = require('fs');
(async () => {
  const out = {};
  try { out.raw_github = (await fetch('https://raw.githubusercontent.com/khang26042012/khang-dsh/main/version.txt', {signal: AbortSignal.timeout(10000)})).status; } catch(e){ out.raw_github = 'FAIL'; }
  try { out.discord = (await fetch('https://discord.com/api/v10/gateway', {signal: AbortSignal.timeout(10000)})).status; } catch(e){ out.discord = 'FAIL'; }
  try { out.python3 = execSync('python3 --version 2>&1').toString().trim(); } catch(e){ out.python3 = 'MISSING'; }
  fs.writeFileSync(__dirname + '/env_report.json', JSON.stringify(out, null, 2));
  console.log('[APP v3]', JSON.stringify(out));
})().catch(e => console.log('[APP FATAL]', String(e).slice(0,80)));
setInterval(() => {}, 60000);
