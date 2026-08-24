// APP WORKER v2 - kham tra moi truong cho bot
const { execSync } = require('child_process');
const fs = require('fs');
console.log('[APP v2] khoi dong');
const info = {};
for (const c of ['python3 --version', 'python --version', 'pip3 --version', 'git --version']) {
  try { info[c] = execSync(c + ' 2>&1').toString().trim().slice(0, 50); }
  catch (e) { info[c] = 'MISSING'; }
}
try { fs.writeFileSync(__dirname + '/env_report.json', JSON.stringify(info, null, 2)); } catch(e){}
console.log('[APP v2] ENV:', JSON.stringify(info));
setInterval(() => console.log('[APP v2] alive'), 120000);
