const RELAY_EPOCH = 1787572630088;
// KHANG RELAY v2 - auto-pull tu GitHub + watchdog + child process
const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const PORT = parseInt(process.env.SERVER_PORT || '26184', 10);
const MIRRORS = [
  'https://raw.githubusercontent.com/khang26042012/khang-dsh/main/',
  'https://cdn.statically.io/gh/khang26042012/khang-dsh/main/'
];
let mi = 0;
async function ghFetch(file) {
  for (let i = 0; i < MIRRORS.length; i++) {
    const base = MIRRORS[(mi + i) % MIRRORS.length];
    try {
      const r = await fetch(base + file + '?t=' + Date.now(), { signal: AbortSignal.timeout(15000) });
      if (r.ok) { mi = (mi + i) % MIRRORS.length; return await r.text(); }
    } catch (e) {}
  }
  throw new Error('tat ca mirror deu loi');
}
const APP_FILE = 'app.js';
const LOCAL_VER_FILE = '.app_version';

let child = null;
let childVersion = '?';
let restartCount = 0;
let desiredVer = '?';

function log(m){ console.log('[RELAY]', new Date().toISOString().slice(11,19), m); }

// ---- CHILD MANAGER + WATCHDOG NOI ----
function startChild(ver) {
  desiredVer = ver;
  if (child) { const old = child; child = null; try { old.kill('SIGKILL'); } catch(e){} }
  childVersion = ver;
  const p = spawn('node', [APP_FILE], { cwd: __dirname, env: { ...process.env, APP_PORT: '30007' }, stdio: ['ignore','inherit','inherit'] });
  child = p;
  log('child start pid=' + p.pid + ' ver=' + ver);
  p.on('exit', (code, sig) => {
    if (child !== p) { log('old child thoat im lang (da thay the)'); return; }
    log('child EXIT code=' + code + ' sig=' + sig + ' -> respawn sau 3s');
    restartCount++;
    setTimeout(() => { if (child === p || child === null) startChild(desiredVer); }, 3000);
  });
}

// ---- AUTO PULL TU GITHUB ----
let pulling = false;
async function pullLatest(manual) {
  if (pulling) return false;
  pulling = true;
  try { return await _pull(manual); } finally { pulling = false; }
}
async function _pull(manual) {
  try {
    const remoteVer = (await ghFetch('version.txt')).trim();
    // TU CAP NHAT RELAY: neu relay.js tren repo khac ban dang chay -> ghi pending roi thoat de watchdog restart
    const remoteRelay = await ghFetch('relay.js');
    const localRelay = fs.readFileSync(__filename, 'utf8');
    const epOf = s => { const m = String(s).match(/RELAY_EPOCH = (\d+)/); return m ? parseInt(m[1]) : 0; };
    if (epOf(remoteRelay) < RELAY_EPOCH) {
      log('BO QUACH relay stale tu CDN (epoch ' + epOf(remoteRelay) + ' < ' + RELAY_EPOCH + ')');
      pulling = false;
      return true;
    }
    if (remoteRelay !== localRelay) {
      fs.writeFileSync(path.join(__dirname, 'relay.js'), remoteRelay);
      log('RELAY CO BAN MOI - ghi xong, thoat de watchdog restart!');
      setTimeout(() => process.exit(0), 500);
      return true;
    }
    let localVer = '';
    try { localVer = fs.readFileSync(path.join(__dirname, LOCAL_VER_FILE), 'utf8').trim(); } catch(e){}
    const epochOf = s => { const m = String(s).match(/-(\d{10,})/); return m ? parseInt(m[1]) : 0; };
    const rE = epochOf(remoteVer), lE = epochOf(localVer);
    if (rE && lE && rE < lE) {
      log('BO QUACH phien ban CDN stale (' + remoteVer + ' < ' + localVer + ') - giu nguyen');
      pulling = false;
      return true;
    }
    if ((remoteVer !== localVer && rE >= lE) || manual) {
      log('UPDATE! ' + localVer + ' -> ' + remoteVer);
      const appText = await ghFetch(APP_FILE);
      fs.writeFileSync(path.join(__dirname, APP_FILE), appText);
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
              child_alive: !!child && child.exitCode === null, restarts: restartCount,
              bot_alive: !!botChild && botChild.exitCode === null, bot_restarts: botRestarts };
  if (req.url === '/ping') { res.writeHead(200, {'Content-Type':'application/json'}); res.end(JSON.stringify(j)); }
  else { res.writeHead(200, {'Content-Type':'text/html; charset=utf-8'});
         res.end('<h1>🐭 Khang Node LIVE</h1><pre>' + JSON.stringify(j,null,2) + '</pre><p><a href="/ping">/ping</a></p>'); }
});
server.listen(PORT, '0.0.0.0', () => log('LISTENING 0.0.0.0:' + PORT));

// ---- BOT MANAGER (Python) ----
let botChild = null;
let botRestarts = 0;
const BOT_DIR = path.join(__dirname, 'bot');
function startBot() {
  const envFile = path.join(BOT_DIR, '.env');
  if (!fs.existsSync(envFile)) { log('BOT DORMANT - chua co bot/.env (token)'); return; }
  if (!fs.existsSync(path.join(BOT_DIR, 'requirements.txt'))) { log('BOT thieu requirements.txt'); return; }
  const doSpawn = () => {
    if (botChild) { try { botChild.kill(); } catch(e){} }
    const b = spawn('python3', ['bot.py'], { cwd: BOT_DIR, stdio: ['ignore','inherit','inherit'] });
    botChild = b;
    log('BOT start pid=' + b.pid);
    b.on('exit', (code, sig) => {
      if (botChild !== b) return;
      log('BOT EXIT code=' + code + ' sig=' + sig + ' -> respawn 15s');
      botRestarts++;
      setTimeout(() => { if (botChild === b || botChild === null) startBot(); }, 15000);
    });
  };
  if (fs.existsSync(path.join(__dirname, '.bot_deps_ok'))) { doSpawn(); return; }
  const { execFile } = require('child_process');
  function ensurePip(cb) {
    execFile('python3', ['-m','pip','--version'], { timeout: 30000 }, (e) => {
      if (!e) { log('pip da co san'); return cb(); }
      log('thieu pip - thu ensurepip...');
      execFile('python3', ['-m','ensurepip','--upgrade'], { timeout: 120000 }, (e2, so2, se2) => {
        if (!e2) { log('ensurepip OK'); return cb(); }
        log('ensurepip FAIL: ' + String(se2||so2).slice(-150));
        log('tai get-pip.py...');
        fetch('https://bootstrap.pypa.io/get-pip.py').then(r => r.text()).then(txt => {
          fs.writeFileSync(path.join(BOT_DIR, 'get-pip.py'), txt);
          execFile('python3', ['get-pip.py', '--break-system-packages'], { cwd: BOT_DIR, timeout: 180000 }, (e3, so3, se3) => {
            if (!e3) { log('get-pip OK'); return cb(); }
            log('get-pip FAIL: ' + String(se3||so3).slice(-200));
            setTimeout(startBot, 300000);
          });
        }).catch(err => { log('tai get-pip loi: ' + String(err).slice(0,100)); setTimeout(startBot, 300000); });
      });
    });
  }
  const tryPip = (args, label, cb) => {
    log('BOT pip ' + label + '...');
    execFile('python3', args, { cwd: BOT_DIR, timeout: 420000, maxBuffer: 4194304 }, (err, so, se) => {
      if (!err) return cb(null);
      const tail = String(se || '').trim().split('\n').slice(-3).join(' | ').slice(0, 220) || String(so).slice(-200);
      log('pip ' + label + ' FAIL: ' + tail);
      cb(err);
    });
  };
  ensurePip(() => tryPip(['-m','pip','install','--no-input','--break-system-packages','-r','requirements.txt'], 'deps', (e1) => {
    if (!e1) return afterDeps();
    log('pip deps van FAIL - thu lai sau 5 phut');
    setTimeout(startBot, 300000);
  }));
  function afterDeps() {
    fs.writeFileSync(path.join(__dirname, '.bot_deps_ok'), new Date().toISOString());
    log('pip install OK - khoi dong bot');
    doSpawn();
  }
}

// ---- BOOT SEQUENCE ----
(async () => {
  log('RELAY-V37-BOOT, port ' + PORT);
  // chay child ban dau voi app hien co (neu chua co file thi tao stub)
  if (!fs.existsSync(path.join(__dirname, APP_FILE))) {
    fs.writeFileSync(path.join(__dirname, APP_FILE), "console.log('[APP] stub - cho pull'); setInterval(()=>{},60000);");
  }
  let bootVer = '?';
  try { bootVer = fs.readFileSync(path.join(__dirname, LOCAL_VER_FILE), 'utf8').trim() || '?'; } catch(e){}
  startChild(bootVer);
  await pullLatest(false);
  startBot();
})();
setInterval(() => pullLatest(false), 5 * 60 * 1000);   // auto pull moi 5 phut
setInterval(() => log('heartbeat child_alive=' + (!!child && child.exitCode===null) + ' restarts=' + restartCount), 120000);
process.on('uncaughtException', e => log('uncaught: ' + String(e).slice(0,120)));
