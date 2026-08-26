# -*- coding: utf-8 -*-
"""KHANG DEV BOT v3 - AGENTIC LOOP kieu harness:
Moi buoc = 1 lan goi API, prefix on dinh de an PROMPT CACHE,
co sleep/backoff khi bi rate-limit, va co tools cay duong that tren host."""
import os, sys, json, time, base64, shlex, logging, subprocess, asyncio
from collections import deque, defaultdict
from pathlib import Path
import aiohttp
import discord
from discord import app_commands

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger('KhangDevBot')

ENV = {}
_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env):
    for line in open(_env, encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            ENV[k.strip()] = v.strip()

TOKEN    = ENV.get('DISCORD_TOKEN', '')
API_BASE = ENV.get('API_BASE', '').rstrip('/')
API_KEY  = ENV.get('API_KEY', '')
MODEL    = ENV.get('MODEL', '')
MV       = ENV.get('MODEL_VISION', MODEL)
RELAY    = ENV.get('RELAY_URL', 'http://127.0.0.1:26184')
EXEC_K   = ENV.get('EXEC_SECRET', '')
WORKDIR  = '/home/container'
MAX_STEPS     = int(ENV.get('MAX_STEPS', '10'))
MAX_TOKENS    = int(ENV.get('MAX_TOKENS', '16384'))
# ---------- API ROTATION POOL ----------
POOL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api_pool.json')

def _default_pool():
    return [{'name': 'env-chinh', 'base': API_BASE, 'key': API_KEY, 'model': MODEL, 'vision': MV}]

def load_pool():
    try:
        data = json.loads(Path(POOL_FILE).read_text(encoding='utf-8'))
        provs = [x for x in data.get('providers', []) if x.get('base') and x.get('model')]
        if provs:
            return provs, int(data.get('active_index', 0))
    except Exception:
        pass
    d = _default_pool()
    return d, 0

_lp, _li = load_pool()
POOL = _lp
PSTATE = {}
ACTIVE = {'i': max(0, min(_li, len(_lp) - 1))}
COOLDOWN_S = 90

def st(name):
    return PSTATE.setdefault(name, {'fails': 0, 'ok': 0, 'cool_until': 0.0, 'last_err': ''})

def ordered_provs(want_img=False):
    n = len(POOL)
    lst = [POOL[(ACTIVE['i'] + k) % n] for k in range(n)]
    if want_img:
        cap = [x for x in lst if x.get('vision')]
        noc = [x for x in lst if not x.get('vision')]
        lst = cap + noc
    return lst

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

SYSTEM_PROMPT = """Ban la Khang Dev Bot - CODING AGENT chay truc tiep tren host Khang server (Linux container). Ban lam viec theo vong lap AGENT: moi luot ban tra loi co the la (a) cau tra loi cuoi cung cho nguoi dung, HOAC (b) goi mot TOOL roi cho ket qua ban se suy nghi tiep o luot sau.

CONG CU BAN CO THE GOI - viet trong the <tool> nhu vay (co the goi nhieu tool trong 1 luot):
<tool>{"name":"run_cmd","args":{"cmd":"ls src/app","cwd":"/home/container/cloner","timeout":60}}</tool>
<tool>{"name":"read_file","args":{"path":"/home/container/cloner/package.json"}}</tool>
<tool>{"name":"write_file","args":{"path":"/home/container/cloner/src/app/page.tsx","content":"...noi dung day du..."}}</tool>
<tool>{"name":"sleep","args":{"seconds":20}}</tool>

Y NGHIA:
- run_cmd: chay lenh shell tai thu muc cwd (mac dinh /home/container/cloner). Binh duoc phep: python3 node npx npm git ls cat grep sed find touch mkdir cp mv tar echo curl chmod pip3. Timeout toi da 180s. Ket qua bi cat gioi han ~3500 ky tu.
- read_file: doc file text (toi da 6000 ky tu dau).
- write_file: ghi file (tao thu muc cha neu thieu). LUON viet content DAY DU khong rut gon.
- sleep: nghi seconds giay (<=120). DUNG sau khi khoi lenh dai nhu npm install/build roi kiem tra lai.

QUY TRINH LAM VIEC CHUAN:
1. Truoc khi sua code: doc file hien tai bang read_file de hieu boi canh.
2. Sua xong: run_cmd kiem tra (vd: npx tsc --noEmit hoac npm run build neu nhanh).
3. Voi lenh dai (npm install/build): goi run_cmd voi timeout lon, neu het gio thi sleep roi kiem tra trang thai.
4. Khi thay doi lon xong: git add -A && git commit -m "mo ta" && git push origin main.
5. Tra loi cuoi cung ngan gon: da lam gi, ket qua the nao, buoc tiep theo la gi.

MOI TRUONG:
- Du an frontend: /home/container/cloner - Next.js 15 App Router + TypeScript + Tailwind + shadcn/ui.
- TUYET DOI khong chay lenh nang tren may chu Minecraft (KhangSMP/KhangSMP2 co nguoi choi)! Moi thao tac chi trong /home/container.
- Port web cloner la 30008. Khong dung 26184 (relay) va 3080 (dsh).
- Proxy VN free (bot2/vnproxy.py): 'python3 /home/container/bot2/vnproxy.py harvest' roi 'check' de lam tuoi; 'get' in 1 proxy song tu xoay; 'status' xem pool. Can di mang qua IP VN thi curl -x http://<proxy> ...
- RAM chung ~4.5GB: npm install lon nen them NODE_OPTIONS=--max-old-space-size=3072.

UI/UX PRO MAX SKILL - BAT BUOC DUNG KHI LAM UI/FRONTEND:
Kho design intelligence tai /home/container/bot2/ui-ux-pro-max (84 UI style, 192 palette mau, 74 cap font, 98 UX guideline).
Truoc khi viet code UI: chay search de lay chuan:
    cd /home/container/bot2/ui-ux-pro-max && python3 src/ui-ux-pro-max/scripts/search.py "<tu khoa>" --domain <domain> --stack nextjs -n 3
Domain: product | style | typography | color | landing | chart | ux | icons | react | web | google-fonts | gsap
Stack: nextjs (du an cloner), shadcn, html-tailwind, react...
Ap dung palette/font/CSS keywords/UX checklist tu ket qua vao code truoc khi tra loi. Ket hop them read_file/readme trong docs/ neu can huong dan sau hon.

QUY TAC TAO APP MOI + RESET/DEPLOY RIENG LE:
- App moi dat tai /home/container/apps/<ten>. Port rieng bat dau tu 30100 tang dan; ghi port vao apps/<ten>/PORT.txt.
- Start app: cd vao thu muc app roi: nohup npm run dev -- -p <port> > app.log 2>&1 & echo $! > run.pid  (production thi npm run build truoc roi npm start -- -p <port>).
- RESET RIENG 1 app (khong anh huong app khac): kill $(cat run.pid) roi chay lai lenh start o tren.
- Deploy lai sau khi sua code production: build lai roi kill+start nhu tren. Xem loi: tail -40 app.log. Kiem tra song: curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:<port>
- Cac dich vu he thong (khong phai app): reset qua http://127.0.0.1:26184/svc-restart?k=<secret>&name=bot|bot2|gw|app|dsh|all - tung cai rieng le.
PHONG CACH: tieng Viet, dan thuc te, khong dai dong. Khi nhan anh: phan tich noi dung anh truoc khi hanh dong."""

history = defaultdict(lambda: deque(maxlen=16))
auto_reply = defaultdict(lambda: True)

# ---------- HTTP / PARSE HELPERS ----------
def extract_first_json(txt):
    start = txt.find('{')
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(txt)):
        ch = txt[i]
        if in_str:
            if esc:
                esc = False
            elif ch == chr(92):
                esc = True
            elif ch == chr(34):
                in_str = False
        else:
            if ch == chr(34):
                in_str = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return txt[start:i+1]
    return None

def collect_sse(txt):
    total = []
    for line in txt.splitlines():
        line = line.strip()
        if not line.startswith('data:'):
            continue
        payload = line[5:].strip()
        if not payload or payload == '[DONE]':
            continue
        try:
            obj = json.loads(payload)
        except Exception:
            continue
        for ch in obj.get('choices') or []:
            delta = ch.get('delta') or {}
            piece = delta.get('content')
            if piece:
                total.append(piece)
    return ''.join(total)

def _has_image(messages):
    for m in messages:
        c = m.get('content')
        if isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and part.get('type') == 'image_url':
                    return True
    return False

async def llm_once(p, messages):
    model = (p.get('vision') or p['model']) if _has_image(messages) else p['model']
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as ses:
        async with ses.post(p['base'].rstrip('/') + '/chat/completions',
                            headers={'Authorization': 'Bearer ' + p.get('key', ''), 'Content-Type': 'application/json'},
                            json={'model': model, 'messages': messages, 'max_tokens': MAX_TOKENS}) as r:
            raw = await r.text()
    sse = collect_sse(raw)
    if sse.strip():
        return sse
    rj = extract_first_json(raw)
    if not rj:
        raise RuntimeError('[body loi] ' + raw[:120])
    data = json.loads(rj)
    if isinstance(data, dict) and data.get('error'):
        err = data['error']
        em = err.get('message', '') if isinstance(err, dict) else str(err)
        raise RuntimeError(em[:250])
    choice = (data.get('choices') or [{}])[0]
    m = choice.get('message', {})
    c = m.get('content')
    if not c or not str(c).strip():
        c = m.get('reasoning') or m.get('reasoning_content') or ''
    if not str(c).strip():
        raise RuntimeError('tra loi rong')
    return str(c)

def is_rate(err):
    low_e = err.lower()
    return ('rate' in low_e) or ('limit' in low_e) or ('429' in low_e) or ('quota' in low_e)

async def call_llm(messages):
    want_img = _has_image(messages)
    errs = []
    for p in ordered_provs(want_img):
        s = st(p['name'])
        if time.time() < s['cool_until']:
            continue
        err = ''
        for attempt in range(2):
            try:
                txt = await llm_once(p, messages)
                s['ok'] += 1
                s['fails'] = 0
                s['last_err'] = ''
                ACTIVE['i'] = POOL.index(p)
                log.info('API[%s] OK (tong %d)', p['name'], s['ok'])
                return txt
            except Exception as e:
                err = str(e)[:200]
            s['fails'] += 1
            s['last_err'] = err
            if is_rate(err):
                break
            if attempt == 0:
                await asyncio.sleep(3)
        s['cool_until'] = time.time() + COOLDOWN_S
        errs.append(p['name'] + ': ' + err[:80])
        log.warning('API[%s] FAIL -> xoay tiep (%s)', p['name'], err[:80])
    return '[Tat ca API deu loi] ' + ' | '.join(errs)[:300]

async def llm_stream(messages, on_chunk):
    """Goi API che do stream; goi on_chunk(text_day_du) nhieu lan de edit tin nhan live."""
    cand = None
    for x in ordered_provs(_has_image(messages)):
        if time.time() >= st(x["name"])["cool_until"]:
            cand = x
            break
    if cand is None:
        cand = ordered_provs(False)[0]
    model = (cand.get("vision") or cand["model"]) if _has_image(messages) else cand["model"]
    acc = []
    last_sent = [0, 0.0]
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as ses:
        async with ses.post(cand["base"].rstrip("/") + "/chat/completions",
                            headers={"Authorization": "Bearer " + cand.get("key", ""), "Content-Type": "application/json"},
                            json={"model": model, "messages": messages, "max_tokens": MAX_TOKENS, "stream": True}) as r:
            buf = ""
            while True:
                piece = await r.content.read(2048)
                if not piece:
                    break
                buf += piece.decode("utf-8", "replace")
                parts = buf.split(chr(10))
                buf = parts.pop()
                for line in parts:
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    pay = line[5:].strip()
                    if not pay or pay == "[DONE]":
                        continue
                    try:
                        obj = json.loads(pay)
                        d = obj.get("choices", [{}])[0].get("delta", {}).get("content")
                        if d:
                            acc.append(d)
                    except Exception:
                        pass
                now = "".join(acc)
                if len(now) - last_sent[0] >= 48 and time.monotonic() - last_sent[1] > 1.1:
                    last_sent[0] = len(now)
                    last_sent[1] = time.monotonic()
                    try:
                        await on_chunk(now)
                    except Exception:
                        pass
    final = "".join(acc)
    ss = st(cand["name"])
    ss["ok"] += 1
    ss["fails"] = 0
    try:
        ACTIVE["i"] = POOL.index(cand)
    except ValueError:
        pass
    if not final.strip():
        return await call_llm(messages)
    return final

async def api_test_all():
    res = []
    for p in POOL:
        t0 = time.time()
        try:
            txt = await llm_once(p, [{'role': 'user', 'content': 'Noi OK'}])
            res.append({'name': p['name'], 'ok': True, 'ms': int((time.time() - t0) * 1000), 'sample': txt[:40]})
        except Exception as e:
            res.append({'name': p['name'], 'ok': False, 'ms': int((time.time() - t0) * 1000), 'err': str(e)[:80]})
    return res
# ---------- TOOL EXECUTOR ----------
ALLOW_BINS = {'python3','node','npx','npm','git','ls','cat','grep','sed','find','touch','mkdir','cp','mv','tar','echo','curl','chmod','pip3'}
def _safe_cmd(cmd):
    try:
        parts = shlex.split(cmd)
    except Exception:
        return False
    return bool(parts) and parts[0] in ALLOW_BINS

def _inside_workdir(pth):
    rp = os.path.realpath(pth)
    return rp.startswith(WORKDIR)

def exec_tool(name, args):
    try:
        if name == 'run_cmd':
            cmd = str(args.get('cmd', ''))[:500]
            cwd = args.get('cwd') or os.path.join(WORKDIR, 'cloner')
            tmo = min(int(args.get('timeout', 60)), 180)
            if not _inside_workdir(str(cwd)):
                return '[TU CHOI] cwd phai nam trong /home/container'
            if not _safe_cmd(cmd):
                return '[TU CHOI] lenh khong thuoc danh sach cho phep: ' + cmd[:100]
            pr = subprocess.run(cmd, shell=True, cwd=str(cwd), capture_output=True, text=True, timeout=tmo)
            out = ((pr.stdout or '') + (chr(10) + pr.stderr if pr.stderr else ''))[-3500:]
            return ('exit=' + str(pr.returncode) + chr(10) + out) if out.strip() else 'exit=0 (khong output)'
        if name == 'read_file':
            pth = str(args.get('path', ''))
            if not _inside_workdir(pth):
                return '[TU CHOI] path ngoai pham vi'
            data = Path(pth).read_text(encoding='utf-8', errors='replace')
            return data[:6000] + (chr(10) + '...(cat)' if len(data) > 6000 else '')
        if name == 'write_file':
            pth = str(args.get('path', ''))
            content = str(args.get('content', ''))
            if not _inside_workdir(pth):
                return '[TU CHOI] path ngoai pham vi'
            Path(pth).parent.mkdir(parents=True, exist_ok=True)
            Path(pth).write_text(content, encoding='utf-8')
            return 'DA GHI ' + pth + ' (' + str(len(content)) + ' ky tu)'
        if name == 'sleep':
            sec = max(1, min(int(float(args.get('seconds', 5))), 120))
            time.sleep(sec)
            return 'da nghi ' + str(sec) + 's'
        return '[LOI] tool khong ton tai: ' + name
    except subprocess.TimeoutExpired:
        return '[HET GIO] lenh chua xong trong timeout - dung sleep roi kiem tra lai'
    except Exception as e:
        return '[LOI TOOL] ' + str(e)[:200]

def parse_tools(text):
    calls = []
    tag_a = '<tool>'
    tag_b = '</tool>'
    pos = 0
    while True:
        i = text.find(tag_a, pos)
        if i == -1:
            break
        j = text.find(tag_b, i)
        if j == -1:
            break
        body = text[i+len(tag_a):j].strip()
        try:
            obj = json.loads(extract_first_json(body) or body)
            if isinstance(obj, dict) and obj.get('name'):
                calls.append((obj['name'], obj.get('args') or {}))
        except Exception:
            pass
        pos = j + len(tag_b)
    return calls

# ---------- AGENT LOOP ----------
async def run_agent(cid, user_content, progress=None, stream_edit=None):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs.extend(history[cid])
    msgs.append({"role": "user", "content": user_content})
    final = None
    for step in range(MAX_STEPS):
        if stream_edit:
            try:
                reply = await llm_stream(msgs, stream_edit)
            except Exception:
                reply = await call_llm(msgs)
        else:
            reply = await call_llm(msgs)
        calls = parse_tools(reply)
        if not calls:
            final = reply
            break
        if progress:
            ten = ", ".join(c[0] for c in calls[:4])
            try:
                await progress("Buoc " + str(step + 1) + ": " + ten)
            except Exception:
                pass
        msgs.append({"role": "assistant", "content": reply})
        feedback = []
        for name, args in calls[:4]:
            res = await asyncio.get_event_loop().run_in_executor(None, exec_tool, name, dict(args))
            feedback.append("[KET QUA " + name + "] " + str(res))
            log.info('step %d tool %s -> %d chars', step, name, len(str(res)))
        msgs.append({"role": "user", "content": chr(10).join(feedback) + chr(10) + "Tiep tuc: tra loi cuoi cung hoac goi tool ke tiep."})
    if final is None:
        final = "(dung o buoc " + str(MAX_STEPS) + " - nhac lai de chay tiep)"
    history[cid].append({"role": "user", "content": str(user_content)[:800] if isinstance(user_content, str) else "(tin nhan kem anh)"})
    history[cid].append({"role": "assistant", "content": str(final)[:2500]})
    return final
async def build_user_content(message, prompt):
    parts = []
    for att in message.attachments:
        ct = att.content_type or ''
        if ct.startswith('image/') and att.size <= 6000000:
            try:
                raw = await att.read()
                b64 = base64.b64encode(raw).decode()
                parts.append({'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (ct, b64)}})
            except Exception as e:
                log.warning('tai anh loi: %s', e)
    if parts:
        return [{'type': 'text', 'text': prompt}] + parts
    return prompt

def help_embed():
    e = discord.Embed(title='Khang Dev Bot v3 (AGENT MODE)', color=0x5865F2)
    e.add_field(name='Agent loop', value='@mention/reply/DM hoac chat bat ky (!auto on) - tu doc/ghi file, chay lenh, build, commit & push', inline=False)
    e.add_field(name='Tools', value='run_cmd | read_file | write_file | sleep (tu goi khi can)', inline=False)
    e.add_field(name='Anh', value='Gui anh kem cau hoi - tu dong chuyen model vision', inline=False)
    e.add_field(name='!status / !reset <ten>', value='Trang thai host / reset rieng le (Admin)', inline=True)
    e.add_field(name='!clear | !auto | !api (xoay API)', value='Quan ly kenh', inline=True)
    return e

async def relay_restart(name):
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as ses:
            async with ses.post(RELAY + '/svc-restart?k=' + EXEC_K + '&name=' + name) as r:
                return r.status == 200, await r.text()
    except Exception as e:
        return False, str(e)[:150]

async def relay_status():
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as ses:
            async with ses.get(RELAY + '/ping') as r:
                j = await r.json()
                lines = []
                lines.append('**Host status**')
                lines.append('- app.js: ' + ('ONLINE' if j.get('child_alive') else 'OFFLINE'))
                lines.append('- bot chinh: ' + ('ONLINE' if j.get('bot_alive') else 'OFFLINE'))
                lines.append('- bot2 (minh): ' + ('ONLINE' if j.get('bot2_alive') else 'OFFLINE'))
                lines.append('- dsh web: ' + ('ONLINE' if j.get('dsh_child_alive') else '?'))
                lines.append('- uptime relay: %ss' % j.get('uptime_s', '?'))
                return chr(10).join(lines)
    except Exception as e:
        return '[Relay khong phan hoi] ' + str(e)[:120]

@bot.event
async def on_ready():
    log.info('Dang nhap OK: %s (ID %s)', bot.user, bot.user.id)
    try:
        await tree.sync()
        log.info('Slash synced')
    except Exception as e:
        log.warning('sync slash loi: %s', e)

@bot.event
async def on_message(message):
    if message.author.id == bot.user.id or message.author.bot:
        return
    stripped = message.content.lstrip('!?/ ').strip()
    low = stripped.lower()
    if low == 'ping':
        await message.reply('Pong! %sms' % round(bot.latency * 1000)); return
    if low in ('help', 'lenh'):
        await message.reply(embed=help_embed()); return
    if low.startswith('reset'):
        if not message.author.guild_permissions.administrator:
            await message.reply('Can quyen Administrator!'); return
        parts_ = stripped.split()
        target = parts_[1] if len(parts_) > 1 else 'app'
        okk, msgg = await relay_restart(target)
        await message.reply(('OK: ' if okk else 'LOI: ') + msgg[:300]); return
    if low == 'status':
        await message.reply(await relay_status()); return
    if low == 'clear':
        history[message.channel.id].clear()
        await message.reply('Da xoa nho kenh nay.'); return
    if low == 'api':
        lines = ['**API Pool - ' + str(len(POOL)) + ' nha cung cap**']
        for idx, pp in enumerate(POOL):
            ss = st(pp['name'])
            mark = 'TRIET-LUC-' if idx == ACTIVE['i'] else '-'
            cool = max(0, int(ss['cool_until'] - time.time()))
            extra = (' | cool:' + str(cool) + 's') if cool else ''
            lines.append(mark + ' ' + pp['name'] + ' [' + pp['model'] + '] ok:' + str(ss['ok']) + ' fail:' + str(ss['fails']) + extra)
        lines.append('Lenh: !api next | !api use <ten> | !api test | !api reload')
        await message.reply(chr(10).join(lines))
        return
    if low.startswith('api next'):
        ACTIVE['i'] = (ACTIVE['i'] + 1) % len(POOL)
        await message.reply('Chuyen sang: ' + POOL[ACTIVE['i']]['name'])
        return
    if low.startswith('api use'):
        ten = stripped.split()[2] if len(stripped.split()) > 2 else ''
        vitri = next((k for k, pp in enumerate(POOL) if pp['name'] == ten), -1)
        if vitri == -1:
            await message.reply('Khong thay. Ten hop le: ' + ', '.join(x['name'] for x in POOL))
        else:
            ACTIVE['i'] = vitri
            await message.reply('Da chon: ' + ten)
        return
    if low == 'api test':
        async with message.channel.typing():
            ketqua = await api_test_all()
        rows = ['**Test toan bo API:**']
        for kk in ketqua:
            icon = 'OK' if kk['ok'] else 'FAIL'
            chi_tiet = kk.get('sample', '') if kk['ok'] else kk.get('err', '')
            rows.append(icon + ' ' + kk['name'] + ' (' + str(kk['ms']) + 'ms) ' + chi_tiet[:60])
        await message.reply(chr(10).join(rows))
        return
    if low == 'api reload':
        moi, vi = load_pool()
        POOL[:] = moi
        PSTATE.clear()
        ACTIVE['i'] = max(0, min(vi, len(moi) - 1))
        await message.reply('Reload xong: ' + str(len(POOL)) + ' provider, dang dung: ' + POOL[ACTIVE['i']]['name'])
        return
    if low.startswith('auto'):
        parts_ = stripped.split()
        arg = parts_[1].lower() if len(parts_) > 1 else ''
        if arg == 'on':
            auto_reply[message.channel.id] = True; await message.reply('BAT auto-reply.')
        elif arg == 'off':
            auto_reply[message.channel.id] = False; await message.reply('TAT auto-reply.')
        else:
            await message.reply('Dung: !auto on | !auto off')
        return
    mentioned = bot.user in message.mentions
    mentions_other_bot = any(u.bot and u.id != bot.user.id for u in message.mentions)
    ref_bot = False
    if message.reference and isinstance(message.reference.resolved, discord.Message):
        ref_bot = message.reference.resolved.author.id == bot.user.id
    is_dm = message.guild is None
    if not ((mentioned or ref_bot or is_dm) or (auto_reply[message.channel.id] and not mentions_other_bot)):
        return
    prompt = message.content.replace('<@%s>' % bot.user.id, '').strip() or 'Phan tich tin nhan nay.'
    content = await build_user_content(message, prompt)
    placeholder = await message.reply(chr(9203) + " Dang suy nghi...")
    last_edit = [0.0]
    async def stream_edit(txt):
        now = time.monotonic()
        if now - last_edit[0] < 1.15:
            return
        last_edit[0] = now
        hien = txt if len(txt) <= 1700 else "..." + txt[-1700:]
        try:
            await placeholder.edit(content=chr(129504) + " " + hien)
        except Exception:
            pass
    async def progress(line):
        try:
            await placeholder.edit(content=chr(128295) + " " + str(line)[:1700])
        except Exception:
            pass
    answer = await run_agent(message.channel.id, content, progress, stream_edit)
    ans = str(answer)
    if len(ans) <= 1900:
        try:
            await placeholder.edit(content=ans)
        except Exception:
            await message.reply(ans[:1900])
    else:
        await placeholder.edit(content=ans[:1900])
        for i in range(1900, len(ans), 1900):
            await message.channel.send(ans[i:i+1900])

@tree.command(name='ping', description='Do tre bot')
async def ping_cmd(inter):
    await inter.response.send_message('Pong! %sms' % round(bot.latency * 1000))

@tree.command(name='help', description='Huong dan')
async def help_cmd(inter):
    await inter.response.send_message(embed=help_embed())

@tree.command(name='status', description='Trang thai dich vu host')
async def status_cmd(inter):
    await inter.response.send_message(await relay_status())

@tree.command(name='clear', description='Xoa nho kenh nay')
async def clear_cmd(inter):
    history[inter.channel_id].clear()
    await inter.response.send_message('Da xoa nho.', ephemeral=True)

@tree.command(name='reset', description='Reset service (Admin)')
@app_commands.describe(target='app | bot | bot2 | dsh | all')
@app_commands.default_permissions(administrator=True)
async def reset_cmd(inter, target: str):
    okk, msgg = await relay_restart(target)
    await inter.response.send_message(('OK: ' if okk else 'LOI: ') + msgg[:300], ephemeral=True)

if __name__ == '__main__':
    if not TOKEN or not API_BASE or not MODEL:
        print('[BOT2] THIEU CONFIG trong .env - thoat')
        sys.exit(1)
    try:
        bot.run(TOKEN, log_handler=None)
    except discord.errors.LoginFailure:
        print('[BOT2] TOKEN SAI/HET HAN')
        sys.exit(1)
