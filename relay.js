const RELAY_EPOCH = 1787677289276;
const EXEC_SECRET = 'khang-ekgwknz4';
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
      setTimeout(() => { try { child && child.kill('SIGKILL'); } catch(e){} try { botChild && botChild.kill('SIGKILL'); } catch(e){} try { lavaChild && lavaChild.kill('SIGKILL'); } catch(e){} setTimeout(() => process.exit(0), 1500); }, 300);
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
// ---- APP BRIDGE helpers: /app/<ten> -> 127.0.0.1:<PORT.txt> ----
const APP_PORT_CACHE = {};
function appPort(name) {
  const now = Date.now();
  if (APP_PORT_CACHE[name] && now - APP_PORT_CACHE[name].t < 5000) return APP_PORT_CACHE[name].port;
  let port = null;
  try { port = parseInt(fs.readFileSync(path.join(__dirname, "apps", name, "PORT.txt"), "utf8").trim(), 10) || null; } catch(e) {}
  APP_PORT_CACHE[name] = { t: now, port: port };
  return port;
}
function appFromReferer(reqLike) {
  const ref = (reqLike.headers && reqLike.headers.referer) || "";
  const i0 = ref.indexOf("/app/");
  if (i0 === -1) return null;
  const rest = ref.slice(i0 + 5);
  const nm = rest.split("/")[0].split("?")[0];
  return nm || null;
}

const server = http.createServer((req, res) => {
  try { fs.appendFileSync("/tmp/hits.log", req.method + " " + req.url + "\n"); } catch(e) {}
  const j = { ok: true, service: 'khang-relay', ver: childVersion, boots_ok: true,
              uptime_s: Math.floor((Date.now()-startedAt)/1000),
              child_alive: !!child && child.exitCode === null, restarts: restartCount,
              bot_alive: !!botChild && botChild.exitCode === null, bot_restarts: botRestarts,
              bot2_alive: typeof bot2Child !== 'undefined' && !!bot2Child && bot2Child.exitCode === null, bot2_restarts: (typeof bot2Restarts !== 'undefined' ? bot2Restarts : 0),
              gw_alive: typeof gwChild !== 'undefined' && !!gwChild && gwChild.exitCode === null,
              tv_alive: typeof tvChild !== 'undefined' && !!tvChild && tvChild.exitCode === null,
              dsh_child_alive: typeof dshChild !== 'undefined' && !!dshChild && dshChild.exitCode === null };
  if (req.url === '/verx') { res.writeHead(200); return res.end('EPOCH=' + RELAY_EPOCH); }
  if (req.url === '/apps') {
    let ds = [];
    try { ds = fs.readdirSync(path.join(__dirname, "apps")).filter(function(d){ return fs.existsSync(path.join(__dirname, "apps", d, "PORT.txt")); }); } catch(e) {}
    res.writeHead(200, {'Content-Type':'application/json'});
    return res.end(JSON.stringify({ ok: true, apps: ds }));
  }
  if (req.url.startsWith('/app/')) {
    const seg = (req.url.slice(5).split('?')[0].split('/')[0] || '').trim();
    if (!seg) { res.writeHead(404); return res.end('Ten app? /app/<ten>/'); }
    const aport = appPort(seg);
    if (!aport) { res.writeHead(404); return res.end('App  + seg +  chua co PORT.txt'); }
    const npath = req.url.replace('/app/' + seg, '') || '/';
    const up = http.request({ hostname: '127.0.0.1', port: aport, path: npath, method: req.method, headers: Object.assign({}, req.headers, { host: '127.0.0.1:' + aport }) }, function(pr){ res.writeHead(pr.statusCode, pr.headers); pr.pipe(res); });
    up.on('error', function(){ try { res.writeHead(502); res.end('App ' + seg + ' khong phan hoi (port ' + aport + ')'); } catch(e){} });
    return req.pipe(up);
  }
  if (req.url.indexOf('/_next/') === 0) {
    const aname = appFromReferer(req);
    const aport = aname ? appPort(aname) : null;
    if (aname && aport) {
      const up = http.request({ hostname: '127.0.0.1', port: aport, path: req.url, method: req.method, headers: Object.assign({}, req.headers, { host: '127.0.0.1:' + aport, referer: 'http://127.0.0.1:' + aport + '/' }) }, function(pr){ res.writeHead(pr.statusCode, pr.headers); pr.pipe(res); });
      up.on('error', function(){ try { res.writeHead(502); res.end('asset loi'); } catch(e){} });
      return req.pipe(up);
    }
  }
  if (req.url.startsWith('/exec?k=')) {
    const { execFile } = require('child_process');
    const u = new URL('http://x' + req.url);
    if (u.searchParams.get('k') !== EXEC_SECRET) { res.writeHead(403); return res.end('forbidden'); }
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const tokenize = (s) => (s.match(/[^\s"']+|"[^"]*"|'[^']*'/g) || []).map(x => x.replace(/^"|"$/g, '').replace(/^'|'$/g, ''));
        const parts = tokenize(JSON.parse(body || '{}').cmd || '');
        const ALLOW = ['yt-dlp','ffmpeg','ffprobe','python3','pip3','ls','cat','whoami','uname','which','node','df','free','ps','java','curl','wget','tail','head','du','git','tar','cp','mv','mkdir','rm','sed','grep','find','touch','chmod','bash'];
        if (!ALLOW.includes(parts[0])) { res.writeHead(400); return res.end('binary khong duoc phep: ' + parts[0]); }
        const bin = parts[0] === 'python3' && parts[1] === '-m' ? 'python3' : parts.shift();
        const args = parts;
        execFile(bin, args, { cwd: __dirname, timeout: 300000, maxBuffer: 2097152 }, (err, so, se) => {
          res.writeHead(200, {'Content-Type':'application/json'});
          const out = ((so||'') + (se ? '\n[STDERR] ' + se : '')).slice(-3500);
          res.end(JSON.stringify({ code: err ? (err.code ?? 1) : 0, out }));
        });
      } catch(e) { res.writeHead(400); res.end('bad json'); }
    });
    return;
  }
  if (req.url.startsWith('/pull?k=')) {
    const u = new URL('http://x' + req.url);
    if (u.searchParams.get('k') !== EXEC_SECRET) { res.writeHead(403); return res.end('forbidden'); }
    let body = '';
    req.on('data', c => body += c);
    req.on('end', async () => {
      try {
        const { url, dest } = JSON.parse(body);
        const r2 = await fetch(url, { redirect: 'follow', signal: AbortSignal.timeout(840000) });
        if (!r2.ok || !r2.body) throw new Error('HTTP ' + r2.status);
        const { Readable } = require('stream');
        const { pipeline } = require('stream/promises');
        const ws = fs.createWriteStream(dest);
        await pipeline(Readable.fromWeb(r2.body), ws);
        const st = fs.statSync(dest);
        log('PULL xong ' + dest + ' ' + Math.floor(st.size/1048576) + 'MB');
        res.writeHead(200, {'Content-Type':'application/json'});
        res.end(JSON.stringify({ ok: true, size: st.size }));
      } catch(e) { res.writeHead(500); res.end(JSON.stringify({ ok: false, err: String(e).slice(0,150) })); }
    });
    return;
  }
  if (req.url.startsWith('/b64w?k=')) {
    const u = new URL('http://x' + req.url);
    if (u.searchParams.get('k') !== EXEC_SECRET) { res.writeHead(403); return res.end('forbidden'); }
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { dest, data } = JSON.parse(body);
        const buf = Buffer.from(data, 'base64');
        fs.writeFileSync(dest, buf);
        log('B64W ghi ' + dest + ' ' + buf.length + 'B');
        res.writeHead(200, {'Content-Type':'application/json'});
        res.end(JSON.stringify({ ok: true, size: buf.length }));
      } catch(e) { res.writeHead(500); res.end(JSON.stringify({ ok: false, err: String(e).slice(0,120) })); }
    });
    return;
  }
  if (req.url.startsWith('/b64w?k=')) {
    const u = new URL('http://x' + req.url);
    if (u.searchParams.get('k') !== EXEC_SECRET) { res.writeHead(403); return res.end('forbidden'); }
    let body = '';
    req.on('data', c => body += c);
    req.on('end', () => {
      try {
        const { dest, data } = JSON.parse(body);
        const buf = Buffer.from(data, 'base64');
        fs.writeFileSync(dest, buf);
        log('B64W ghi ' + dest + ' ' + buf.length + 'B');
        res.writeHead(200, {'Content-Type':'application/json'});
        res.end(JSON.stringify({ ok: true, size: buf.length }));
      } catch(e) { res.writeHead(500); res.end(JSON.stringify({ ok: false, err: String(e).slice(0,120) })); }
    });
    return;
  }
  if (req.url.startsWith('/svc-restart?')) {
    const u = new URL('http://x' + req.url);
    if (u.searchParams.get('k') !== EXEC_SECRET) { res.writeHead(403); return res.end('forbidden'); }
    const nm = (u.searchParams.get('name') || '').toLowerCase();
    if (nm === 'bot' || nm === 'bot2' || nm === 'gw' || nm === 'app' || nm === 'tv' || nm === 'all' || nm === 'dsh') {
      if (nm === 'dsh') { setTimeout(() => startDsh(), 1500); res.writeHead(200, {'Content-Type':'application/json'}); return res.end(JSON.stringify({ ok:true, restarted:'dsh' })); }
      log('SVC-RESTART yeu cau: ' + nm);
      if (nm === 'bot2') {
        const oldB2 = bot2Child; bot2Child = null;
        try { oldB2 && oldB2.kill('SIGKILL'); } catch(e){}
        setTimeout(() => startBot2(), 2000);
        res.writeHead(200, {'Content-Type':'application/json'});
        return res.end(JSON.stringify({ ok:true, restarted:'bot2' }));
      }
      if (nm === 'tv') {
        const oldTv = tvChild; tvChild = null;
        try { oldTv && oldTv.kill('SIGKILL'); } catch(e){}
        setTimeout(() => startTv(), 1500);
      }
      if (nm === 'gw') {
        const oldGw = gwChild; gwChild = null;
        try { oldGw && oldGw.kill('SIGKILL'); } catch(e){}
        setTimeout(() => startGw(), 1500);
        res.writeHead(200, {'Content-Type':'application/json'});
        return res.end(JSON.stringify({ ok:true, restarted:'gw' }));
      }
      if (nm === 'bot' || nm === 'all') {
        const oldBot = botChild; botChild = null;   // cam exit-handler tu respawn
        try { oldBot && oldBot.kill('SIGKILL'); } catch(e){}
        setTimeout(() => startBot(), 2000);
      }
      if (nm === 'app' || nm === 'all') {
        const ver = childVersion !== '?' ? childVersion : desiredVer;
        setTimeout(() => startChild(ver), 2000);
      }
      res.writeHead(200, {'Content-Type':'application/json'});
      return res.end(JSON.stringify({ ok:true, restarted: nm }));
    }
    res.writeHead(400, {'Content-Type':'application/json'});
    return res.end(JSON.stringify({ ok:false, err:'name phai la: bot | bot2 | app | dsh | all' }));
  }
  if (req.url === '/ping') { res.writeHead(200, {'Content-Type':'application/json'}); res.end(JSON.stringify(j)); }
  else if (dshChild && !dshChild.killed) { proxyReq(req, res); }
  else { res.writeHead(200, {'Content-Type':'text/html; charset=utf-8'});
         res.end('<h1>🐭 Khang Node LIVE</h1><pre>' + JSON.stringify(j,null,2) + '</pre><p><a href="/ping">/ping</a></p><p>DSH: chua khoi dong</p>'); }
});
server.listen(PORT, '0.0.0.0', () => log('LISTENING 0.0.0.0:' + PORT));

// ---- BOT MANAGER (Python) ----
let botChild = null;
let botRestarts = 0;
const BOT_DIR = path.join(__dirname, 'bot');
function startBot() {
  killOrphans(['--svc=main']);
  const envFile = path.join(BOT_DIR, '.env');
  if (!fs.existsSync(envFile)) { log('BOT DORMANT - chua co bot/.env (token)'); return; }
  if (!fs.existsSync(path.join(BOT_DIR, 'requirements.txt'))) { log('BOT thieu requirements.txt'); return; }
  const doSpawn = () => {
    if (botChild) { try { botChild.kill(); } catch(e){} }
    const b = spawn('python3', ['bot.py', '--svc=main'], { cwd: BOT_DIR, stdio: ['ignore','inherit','inherit'] });
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

// ---- LAVALINK MANAGER (Java) ----
// ---- BOT2 MANAGER (Khang Dev Bot) ----
let bot2Child = null;
let bot2Restarts = 0;
const BOT2_DIR = path.join(__dirname, 'bot2');
function startBot2() {
  killOrphans(['--svc=dev']);
  if (!fs.existsSync(path.join(BOT2_DIR, '.env'))) { log('BOT2 DORMANT - chua co bot2/.env'); return; }
  const p = spawn('python3', ['bot.py', '--svc=dev'], { cwd: BOT2_DIR, stdio: ['ignore','inherit','inherit'] });
  bot2Child = p;
  log('BOT2 start pid=' + p.pid);
  p.on('exit', (code, sig) => {
    if (bot2Child !== p) return;
    log('BOT2 EXIT code=' + code + ' sig=' + sig + ' -> respawn 15s');
    bot2Restarts++;
    setTimeout(() => { if (bot2Child === p || bot2Child === null) startBot2(); }, 15000);
  });
}
setTimeout(startBot2, 12000);

// ---- API GATEWAY MANAGER (cong chung cho cac bot) ----
let gwChild = null;
const GW_DIR = path.join(__dirname, 'bot2');
function startGw() {
  killOrphans(['api_gateway.py']);
  if (!fs.existsSync(path.join(GW_DIR, 'api_gateway.py'))) { log('GW khong co file - bo qua'); return; }
  const pg = spawn('python3', ['api_gateway.py'], { cwd: GW_DIR, stdio: ['ignore','inherit','inherit'] });
  gwChild = pg;
  log('GW start pid=' + pg.pid);
  pg.on('exit', (code, sig) => {
    if (gwChild !== pg) return;
    log('GW EXIT code=' + code + ' -> respawn 10s');
    setTimeout(() => { if (gwChild === pg || gwChild === null) startGw(); }, 10000);
  });
}
let tvChild = null;
let tvRestarts = 0;
function startTv() {
  killOrphans(['tgvision.py']);
  const ptv = spawn('python3', ['tgvision.py'], { cwd: BOT2_DIR, stdio: ['ignore','inherit','inherit'] });
  tvChild = ptv;
  log('TVISION start pid=' + ptv.pid);
  ptv.on('exit', (code, sig) => {
    if (tvChild !== ptv) return;
    log('TVISION EXIT code=' + code + ' sig=' + sig + ' -> respawn 15s');
    tvRestarts++;
    setTimeout(() => { if (tvChild === ptv || tvChild === null) startTv(); }, 15000);
  });
}
setTimeout(startGw, 8000);
setTimeout(startTv, 9500);

// ---- DSH WEB HARNESS MANAGER ----
let dshChild = null;
const DSH_PORT = 3080;
function startDsh() {
  const dshBin = path.join(__dirname, 'dsh-app', 'node_modules', '@deepseek-ai', 'dsh', 'lib', 'bin.js');
  if (!fs.existsSync(dshBin)) { log('DSH chua cai dat (thieu dsh-app)'); return; }
  if (dshChild) { try { dshChild.kill('SIGKILL'); } catch(e){} }
  const p = spawn('node', ['--expose-internals', dshBin, '--profile', 'web', '--host', '127.0.0.1', '--port', String(DSH_PORT), '--trusted-host', 'nvnmc.asia:26184', '--trusted-host', 'nvnmc.asia', '--trusted-host', '202.55.135.45:26184', '--trusted-host', 'localhost:26184'], {
    cwd: __dirname,
    env: { ...process.env, DSH_HOME: path.join(__dirname, '.dsh-home'), DSH_PASSWORD: process.env.DSH_WEB_PASS || 'khang2026', DSH_TELEMETRY_DISABLED: '1', NVN_API_KEY: 'sk-0fc648aa8d074f59-4tiy6p-7efc95e5', HOME: __dirname },
    stdio: ['ignore','inherit','inherit']
  });
  dshChild = p;
  log('DSH start pid=' + p.pid);
  p.on('exit', (code, sig) => {
    if (dshChild !== p) return;
    log('DSH EXIT code=' + code + ' -> respawn 10s');
    setTimeout(() => { if (dshChild === p || dshChild === null) startDsh(); }, 10000);
  });
}
setTimeout(startDsh, 8000);

// ---- REVERSE PROXY /dsh -> 127.0.0.1:3080 (bao gom websocket) ----
const proxyReq = (req2, res2) => {
  const opts = { hostname: '127.0.0.1', port: DSH_PORT, path: req2.url, method: req2.method, headers: { ...req2.headers, host: req2.headers.host || ('nvnmc.asia:' + PORT) } };
  const up = http.request(opts, (pr) => { res2.writeHead(pr.statusCode, pr.headers); pr.pipe(res2); });
  up.on('error', () => { try { res2.writeHead(502); res2.end('DSH chua san sang'); } catch(e){} });
  req2.pipe(up);
};
server.on('upgrade', (req2, sock, head) => {
  {
    const aname = appFromReferer(req2);
    const aport = aname ? appPort(aname) : null;
    if (aname && aport) {
      const upa = http.request({ hostname: '127.0.0.1', port: aport, path: req2.url, headers: req2.headers });
      upa.on("upgrade", function(pres, psock, phead) {
        const lines = ["HTTP/1.1 101 Switching Protocols"];
        for (const kv of Object.entries(pres.headers)) lines.push(kv[0] + ": " + kv[1]);
        sock.write(lines.join("\r\n") + "\r\n\r\n");
        psock.pipe(sock); sock.pipe(psock);
      });
      upa.on("error", function(){ try { sock.destroy(); } catch(e){} });
      return upa.end(head);
    }
  }
  const opts = { hostname: '127.0.0.1', port: DSH_PORT, path: req2.url, headers: req2.headers };
  const up = http.request(opts);
  up.on('upgrade', (pres, psock, phead) => {
    const lines = [];
    lines.push('HTTP/1.1 101 Switching Protocols');
    for (const [k,v] of Object.entries(pres.headers)) lines.push(k + ': ' + v);
    sock.write(lines.join('\r\n') + '\r\n\r\n');
    psock.pipe(sock); sock.pipe(psock);
  });
  up.on('error', () => { try { sock.destroy(); } catch(e){} });
  up.end(head);
});

let lavaChild = null;
let lavaRestarts = 0;
const LAVA_DIR = path.join(__dirname, 'lava');
function killOrphans(markers) {
  try {
    for (const pid of fs.readdirSync('/proc').filter(x => /^\d+$/.test(x))) {
      if (+pid === process.pid) continue;
      try {
        const cmd = fs.readFileSync('/proc/' + pid + '/cmdline', 'utf8');
        if (markers.some(m => cmd.includes(m))) { process.kill(+pid, 'SIGKILL'); log('DIET ORPHAN ' + pid + ': ' + cmd.slice(0,60)); }
      } catch(e) {}
    }
  } catch(e) {}
}
function startLava() { /* TINH NANG NHAC DA GO BO theo yeu chu - 2026/08/24 */ }

// ---- BOOT SEQUENCE ----
(async () => {
  log('RELAY-V48-BOOT, port ' + PORT);
  // chay child ban dau voi app hien co (neu chua co file thi tao stub)
  if (!fs.existsSync(path.join(__dirname, APP_FILE))) {
    fs.writeFileSync(path.join(__dirname, APP_FILE), "console.log('[APP] stub - cho pull'); setInterval(()=>{},60000);");
  }
  let bootVer = '?';
  try { bootVer = fs.readFileSync(path.join(__dirname, LOCAL_VER_FILE), 'utf8').trim() || '?'; } catch(e){}
  startChild(bootVer);
  await pullLatest(false);
  // startLava da bo (tinh nang nhac duoc go bo)
  setTimeout(startBot, 8000);
})();
setInterval(() => pullLatest(false), 5 * 60 * 1000);   // auto pull moi 5 phut
setInterval(() => log('heartbeat child_alive=' + (!!child && child.exitCode===null) + ' restarts=' + restartCount), 120000);
process.on('uncaughtException', e => log('uncaught: ' + String(e).slice(0,120)));
