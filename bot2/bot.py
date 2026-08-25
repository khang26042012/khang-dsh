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

CODE FRONTEND: Next.js 15 App Router, dan dau dong 'use client' khi dung hook/event, Tailwind utilities, shadcn/ui, Route Handlers tai src/app/api/*/route.ts tra JSON. Viet code day du import, chay duoc ngay.

PHONG CACH: tieng Viet ngan gon, vi du thuc te. Khi nhan anh: mo ta va phan tich chi tiet noi dung anh."""

history = defaultdict(lambda: deque(maxlen=14))

def build_messages(cid, user_content):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs.extend(history[cid])
    msgs.append({"role": "user", "content": user_content})
    return msgs

async def call_llm(messages):
    try:
        timeout = aiohttp.ClientTimeout(total=180)
        async with aiohttp.ClientSession(timeout=timeout) as ses:
            async with ses.post(API_BASE + '/chat/completions',
                                headers={'Authorization': 'Bearer ' + API_KEY, 'Content-Type': 'application/json'},
                                json={'model': MODEL, 'messages': messages}) as r:
                if r.status != 200:
                    return '[Loi %s tu router] %s' % (r.status, (await r.text())[:250])
                data = await r.json()
                return data['choices'][0]['message']['content'] or '(rong)'
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
    if not (mentioned or ref_bot or is_dm):
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
