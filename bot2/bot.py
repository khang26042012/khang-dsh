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
- RAM chung ~4.5GB: npm install lon nen them NODE_OPTIONS=--max-old-space-size=3072.

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

async def llm_once(messages):
    """Mot lan goi API - tra (text, err). Khong retry o day."""
    timeout = aiohttp.ClientTimeout(total=300)
    async with aiohttp.ClientSession(timeout=timeout) as ses:
        async with ses.post(API_BASE + '/chat/completions',
                            headers={'Authorization': 'Bearer ' + API_KEY, 'Content-Type': 'application/json'},
                            json={'model': (MV if _has_image(messages) else MODEL),
                                  'messages': messages, 'max_tokens': MAX_TOKENS}) as r:
            raw = await r.text()
    sse = collect_sse(raw)
    if sse.strip():
        return sse, None
    rj = extract_first_json(raw)
    if not rj:
        return None, '[Router tra body loi] ' + raw[:150]
    data = json.loads(rj)
    if isinstance(data, dict) and data.get('error'):
        err = data['error']
        em = err.get('message', '') if isinstance(err, dict) else str(err)
        return None, em[:250]
    choice = (data.get('choices') or [{}])[0]
    m = choice.get('message', {})
    c = m.get('content')
    if not c or not str(c).strip():
        c = m.get('reasoning') or m.get('reasoning_content') or ''
    if not str(c).strip():
        return None, '(tra loi rong)'
    return str(c), None

async def call_llm(messages):
    """Goi API co RETRY + SLEEP backoff mu: 3s -> 8s -> 20s khi loi/429."""
    waits = [0, 3, 8, 20]
    last_err = ''
    for attempt, w in enumerate(waits):
        if w:
            log.info('retry %ds sau loi: %s', w, last_err[:80])
            await asyncio.sleep(w)
        txt, err = await llm_once(messages)
        if txt is not None:
            return txt
        last_err = err or ''
        low = last_err.lower()
        if 'rate' in low or 'limit' in low or '429' in low:
            continue
        if attempt >= 1:
            break
    return '[Loi router sau retry] ' + last_err[:200]

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
async def run_agent(cid, user_content):
    msgs = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    msgs.extend(history[cid])
    msgs.append({'role': 'user', 'content': user_content})
    final = None
    for step in range(MAX_STEPS):
        reply = await call_llm(msgs)
        calls = parse_tools(reply)
        if not calls:
            final = reply
            break
        msgs.append({'role': 'assistant', 'content': reply})
        feedback = []
        for name, args in calls[:4]:
            res = await asyncio.get_event_loop().run_in_executor(None, exec_tool, name, dict(args))
            feedback.append('[KET QUA ' + name + '] ' + str(res))
            log.info('step %d tool %s -> %d chars', step, name, len(str(res)))
        msgs.append({'role': 'user', 'content': chr(10).join(feedback) + chr(10) + 'Tiep tuc: tra loi cuoi cung hoac goi tool ke tiep.'})
    if final is None:
        final = '(dung o buoc ' + str(MAX_STEPS) + ' - nhac "!tiep" de cho chay tiep)'
    # Luu lich su rut gon (giu prefix on dinh de an cache)
    history[cid].append({'role': 'user', 'content': str(user_content)[:800] if isinstance(user_content, str) else '(tin nhan kem anh)'})
    history[cid].append({'role': 'assistant', 'content': str(final)[:2500]})
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
    e.add_field(name='!clear / !auto on|off / !ping', value='Quan ly kenh', inline=True)
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
    async with message.channel.typing():
        content = await build_user_content(message, prompt)
        answer = await run_agent(message.channel.id, content)
    for i in range(0, len(str(answer)), 1900):
        await message.reply(str(answer)[i:i+1900])

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
