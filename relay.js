// KHANG RELAY v2 - auto-pull tu GitHub + watchdog + child process
const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const PORT = parseInt(process.env.SERVER_PORT || '26184', 10);
const GH_BASE = 'https://raw.githubusercontent.com/khang26042012/khang-dsh/main/';
const VERSION_URL = GH_BASE + 'version.txt';
const APP_FILE = 'app.js';
const LOCAL_VER_FILE = '.app_version';

let child = null;
let childVersion = '?';
let restartCount = 0;

function log(m){ console.log('[RELAY]', new Date().toISOString().slice(11,19), m); }

// ---- CHILD MANAGER + WATCHDOG NOI ----
function startChild(ver) {
  if (child) { try { child.kill('SIGKILL'); } catch(e){} }
  childVersion = ver;
  const p = spawn('node', [APP_FILE], { cwd: __dirname, env: { ...process.env, APP_PORT: '30007' }, stdio: ['ignore','inherit','inherit'] });
  child = p;
  log('child start pid=' + p.pid + ' ver=' + ver);
  p.on('exit', (code, sig) => {
    log('child EXIT code=' + code + ' sig=' + sig + ' -> respawn sau 3s');
    restartCount++;
    setTimeout(() => startChild(childVersion), 3000);
  });
}

// ---- AUTO PULL TU GITHUB ----
async function pullLatest(manual) {
  try {
    const r = await fetch(VERSION_URL + '?t=' + Date.now(), { signal: AbortSignal.timeout(15000) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const remoteVer = (await r.text()).trim();
    let localVer = '';
    try { localVer = fs.readFileSync(path.join(__dirname, LOCAL_VER_FILE), 'utf8').trim(); } catch(e){}
    if (remoteVer !== localVer || manual) {
      log('UPDATE! ' + localVer + ' -> ' + remoteVer);
      const ar = await fetch(GH_BASE + APP_FILE + '?t=' + Date.now(), { signal: AbortSignal.timeout(20000) });
      if (!ar.ok) throw new Error('app HTTP ' + ar.status);
      fs.writeFileSync(path.join(__dirname, APP_FILE), await ar.text());
      fs.writeFileSync(path.join(__dirname, LOCAL_VER_FILE), remoteVer);
      log('da ghi ' + APP_FILE + ' ver=' + remoteVer + ' - restart child');
      startChild(remoteVer);
    } else if (manual) {
      log('da la phien ban moi nhat: ' + localVer);
    }
    return true;
  } catch (e) {
    log('pull loi: ' + String(e).slice(0, 80));
    return false;
  }
}

// ---- HTTP PUBLIC ----
let startedAt = Date.now();
const server = http.createServer((req, res) => {
  const j = { ok: true, service: 'khang-relay', ver: childVersion, boots_ok: true,
              uptime_s: Math.floor((Date.now()-startedAt)/1000),
              child_alive: !!child && child.exitCode === null, restarts: restartCount };
  if (req.url === '/ping') { res.writeHead(200, {'Content-Type':'application/json'}); res.end(JSON.stringify(j)); }
  else { res.writeHead(200, {'Content-Type':'text/html; charset=utf-8'});
         res.end('<h1>🐭 Khang Node LIVE</h1><pre>' + JSON.stringify(j,null,2) + '</pre><p><a href="/ping">/ping</a></p>'); }
});
server.listen(PORT, '0.0.0.0', () => log('LISTENING 0.0.0.0:' + PORT));

// ---- BOOT SEQUENCE ----
(async () => {
  log('relay v2 boot, port ' + PORT);
  // chay child ban dau voi app hien co (neu chua co file thi tao stub)
  if (!fs.existsSync(path.join(__dirname, APP_FILE))) {
    fs.writeFileSync(path.join(__dirname, APP_FILE), "console.log('[APP] stub - cho pull'); setInterval(()=>{},60000);");
  }
  startChild('?');
  await pullLatest(false);
})();
setInterval(() => pullLatest(false), 5 * 60 * 1000);   // auto pull moi 5 phut
setInterval(() => log('heartbeat child_alive=' + (!!child && child.exitCode===null) + ' restarts=' + restartCount), 120000);
process.on('uncaughtException', e => log('uncaught: ' + String(e).slice(0,120)));
