# -*- coding: utf-8 -*-
"""KHANG DEV BOT - tro ly lap trinh tren host (frontend coder companion)."""
import os, sys, json, asyncio, logging
from collections import deque, defaultdict
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
API_BASE = ENV.get('API_BASE', 'https://1-production-6390.up.railway.app/v1').rstrip('/')
API_KEY  = ENV.get('API_KEY', '')
MODEL    = ENV.get('MODEL', 'openrouter/stealth/ox-alpha')
MV = ENV.get('MODEL_VISION', 'Xkiro/deepseek/deepseek-v4-flash-vision-exp')
RELAY    = ENV.get('RELAY_URL', 'http://127.0.0.1:26184')
EXEC_K   = ENV.get('EXEC_SECRET', '')

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

SYSTEM_PROMPT = """Ban la Khang Dev Bot - tro ly lap trinh cua chu Phan Trong Khang, lam viec TRUC TIEP tren host Khang server (Pterodactyl Linux container).

MOI TRUONG:
- Du an frontend: /home/container/cloner - Next.js 15 App Router + TypeScript + Tailwind + shadcn/ui (tu template ai-website-cloner-template).
- Chia doi cong viec: mot coder khac lam FRONTEND; ban ho tro backend/hau can va giai dap moi ky thuat.
- Relay dich vu tai http://127.0.0.1:26184:
    GET /ping -> trang thai app.js/bot/bot2/dsh
    POST /svc-restart?k=<secret>&name=app|bot|bot2|dsh|all -> reset rieng le khong anh huong service khac
    POST /exec?k=<secret> body {"cmd":"..."} -> chay lenh host (allowlist bash/python3/git/node/curl/...)
- DSH web harness o port noi bo 3080, proxy ra public.

GIT CHUAN (remote da cam token, push truc tiep duoc):
    cd /home/container/cloner
    git add -A && git commit -m "mo ta"
    git push origin main
    # neu mang chan github -> them tien to mirror: https://ghproxy.net/<url_daydu>

RESET CHUAN:
    - Frontend dev mode: hot reload, khong can restart. Production: svc-restart name=app
    - Bot: /reload (execv giu PID) hoac svc-restart name=bot
    - all: chi khi that su can.

PHAM VI DEPLOY - DOC KY - SAI LA CHET:
- Container nay (Khang host) LA NOI DUY NHAT duoc phep chay lenh nang (npm install/build/start). Tat ca thao tac code deu tai /home/container/cloner.
- TUYET DOI KHONG huong dan, goi y, hoac tao lenh de chay bat ky gi tren cac MAY CHU MINECRAFT (KhangSMP, KhangSMP2 - dang co nguoi choi online)! Chi 1 lan npm install o day cung lam lag/cai chet ca may chu game. Neu nguoi dung hoi ve deploy tren MC host: tu choi nem nhe va huong ve day.
- Truoc moi lenh nang: (1) pwd xac nhan dung thu muc, (2) git commit truoc da, (3) npm/install lon thi them NODE_OPTIONS=--max-old-space-size=3072 vi container chung song voi relay + 2 bot + dsh web (tran ~4.5GB RAM).
- Chay web cloner: DEV: cd /home/container/cloner && npm run dev -- -p 30008 | PRODUCTION: npm run build && npm start -- -p 30008. Port 30008 danh rieng cho no; KHONG DUNG port 26184 (relay) va 3080 (dsh web).
- Sau thay doi lon: git commit + push NGAY de co backup.

CODE FRONTEND: Next.js 15 App Router, dan dau dong 'use client' khi dung hook/event, Tailwind utilities, shadcn/ui, Route Handlers tai src/app/api/*/route.ts tra JSON. Viet code day du import, chay duoc ngay.

PHONG CACH: tieng Viet ngan gon, vi du thuc te. Khi nhan anh: mo ta va phan tich chi tiet noi dung anh."""

history = defaultdict(lambda: deque(maxlen=14))
auto_reply = defaultdict(lambda: True)

def build_messages(cid, user_content):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs.extend(history[cid])
    msgs.append({"role": "user", "content": user_content})
    return msgs

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

def extract_first_json(txt):
    DQ = chr(34)
    BS = chr(92)
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
            elif ch == BS:
                esc = True
            elif ch == DQ:
                in_str = False
        else:
            if ch == DQ:
                in_str = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return txt[start:i+1]
    return None

def _has_image(messages):
    for m in messages:
        c = m.get('content')
        if isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and part.get('type') == 'image_url':
                    return True
    return False

async def call_llm(messages):
    try:
        timeout = aiohttp.ClientTimeout(total=240)
        async with aiohttp.ClientSession(timeout=timeout) as ses:
            async with ses.post(API_BASE + '/chat/completions',
                                headers={'Authorization': 'Bearer ' + API_KEY, 'Content-Type': 'application/json'},
                                json={'model': (MV if _has_image(messages) else MODEL), 'messages': messages}) as r:
                raw = await r.text()
        sse_text = collect_sse(raw)
        if sse_text.strip():
            return sse_text
        raw_json = extract_first_json(raw)
        if not raw_json:
            return '[Router tra body loi] ' + raw[:200]
        data = json.loads(raw_json)
        if isinstance(data, dict) and data.get('error'):
            err = data['error']
            em = err.get('message', '') if isinstance(err, dict) else str(err)
            low_em = em.lower()
            if 'rate' in low_em or 'limit' in low_em or '429' in low_em:
                return '[Het luot free mot chut - thu lai sau vai giay nhe]'
            return '[Router bao loi] ' + em[:250]
        choice = (data.get('choices') or [{}])[0]
        m = choice.get('message', {})
        c = m.get('content')
        if not c or not str(c).strip():
            c = m.get('reasoning') or m.get('reasoning_content') or ''
        if not str(c).strip():
            return '(Model chi suy nghi chua kip tra loi - thu lai nhe)'
        return c
    except Exception as e:
        return '[Loi ket noi router] ' + str(e)[:200]
async def build_user_content(message, prompt):
    parts = []
    for att in message.attachments:
        ct = att.content_type or ''
        if ct.startswith('image/') and att.size <= 6000000:
            try:
                raw = await att.read()
                import base64
                b64 = base64.b64encode(raw).decode()
                parts.append({'type': 'image_url', 'image_url': {'url': 'data:%s;base64,%s' % (ct, b64)}})
            except Exception as e:
                log.warning('tai anh loi: %s', e)
    if parts:
        return [{'type': 'text', 'text': prompt}] + parts
    return prompt

def chunk(text, limit=1900):
    out = []
    while len(text) > limit:
        cut = text.rfind('\n', 0, limit)
        if cut == -1:
            cut = limit
        out.append(text[:cut])
        text = text[cut:].lstrip()
    out.append(text)
    return out

def help_embed():
    e = discord.Embed(title='Khangu Dev Bot - Lenh', color=0x5865F2)
    e.add_field(name='Chat AI', value='@mention / reply / DM - tu dong tra loi, ho tro gui ANH', inline=False)
    e.add_field(name='!ping', value='Do tre', inline=True)
    e.add_field(name='!status', value='Trang thai host', inline=True)
    e.add_field(name='!reset <ten>', value='app|bot|bot2|dsh|all (Admin)', inline=True)
    e.add_field(name='!clear', value='Xoa nho kenh', inline=True)
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
        log.info('Slash commands synced')
    except Exception as e:
        log.warning('sync slash loi: %s', e)

@bot.event
async def on_message(message):
    if message.author.id == bot.user.id or message.author.bot:
        return
    mentioned = bot.user in message.mentions
    ref_bot = False
    if message.reference and isinstance(message.reference.resolved, discord.Message):
        ref_bot = message.reference.resolved.author.id == bot.user.id
    is_dm = message.guild is None
    mentions_other_bot = any(u.bot and u.id != bot.user.id for u in message.mentions)
    should_ai = (mentioned or ref_bot or is_dm) or (auto_reply[message.channel.id] and not mentions_other_bot)
    if not should_ai:
        return
    stripped = message.content.lstrip('!?/ ').strip()
    low = stripped.lower()
    if low == 'ping':
        await message.reply('Pong! %sms' % round(bot.latency * 1000))
        return
    if low in ('help', 'lenh'):
        await message.reply(embed=help_embed())
        return
    if low.startswith('reset'):
        if not message.author.guild_permissions.administrator:
            await message.reply('Can quyen Administrator!')
            return
        parts_ = stripped.split()
        target = parts_[1] if len(parts_) > 1 else 'app'
        okk, msgg = await relay_restart(target)
        await message.reply(('OK: ' if okk else 'LOI: ') + msgg[:300])
        return
    if low == 'status':
        await message.reply(await relay_status())
        return
    if low.startswith('auto'):
        parts_ = stripped.split()
        arg = parts_[1].lower() if len(parts_) > 1 else ''
        if arg == 'on':
            auto_reply[message.channel.id] = True
            await message.reply('BAT auto-reply cho kenh nay.')
        elif arg == 'off':
            auto_reply[message.channel.id] = False
            await message.reply('TAT auto-reply cho kenh nay.')
        else:
            await message.reply('Dung: !auto on  hoac  !auto off')
        return
    if low == 'clear':
        history[message.channel.id].clear()
        await message.reply('Da xoa nho kenh nay.')
        return
    prompt = message.content.replace('<@%s>' % bot.user.id, '').strip() or 'Phan tich tin nhan nay.'
    async with message.channel.typing():
        content = await build_user_content(message, prompt)
        answer = await call_llm(build_messages(message.channel.id, content))
        history[message.channel.id].append({'role': 'user', 'content': prompt[:500]})
        history[message.channel.id].append({'role': 'assistant', 'content': str(answer)[:1500]})
    for part in chunk(str(answer)):
        await message.reply(part[:1900])

@tree.command(name='ping', description='Do tre bot')
async def ping_cmd(inter):
    await inter.response.send_message('Pong! %sms' % round(bot.latency * 1000))

@tree.command(name='help', description='Danh sach lenh')
async def help_cmd(inter):
    await inter.response.send_message(embed=help_embed())

@tree.command(name='status', description='Trang thai dich vu host')
async def status_cmd(inter):
    await inter.response.send_message(await relay_status())

@tree.command(name='clear', description='Xoa nho hoi thoai kenh nay')
async def clear_cmd(inter):
    history[inter.channel_id].clear()
    await inter.response.send_message('Da xoa nho.', ephemeral=True)

@tree.command(name='reset', description='Reset service tren host (Admin)')
@app_commands.describe(target='app | bot | bot2 | dsh | all')
@app_commands.default_permissions(administrator=True)
async def reset_cmd(inter, target: str):
    okk, msgg = await relay_restart(target)
    await inter.response.send_message(('OK: ' if okk else 'LOI: ') + msgg[:300], ephemeral=True)

if not TOKEN:
    print('[BOT2] THIEU DISCORD_TOKEN trong .env - thoat de khong respawn vo nghia')
    sys.exit(1)

try:
    bot.run(TOKEN, log_handler=None)
except discord.errors.LoginFailure:
    print('[BOT2] TOKEN SAI/HET HAN')
    sys.exit(1)
