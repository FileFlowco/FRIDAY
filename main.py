#!/usr/bin/env python3
"""
FRIDAY — Main Launcher
Runs Telegram bot + Web Dashboard concurrently on the same process.
Web dashboard: http://localhost:7771
"""

import os
import asyncio
import logging
import webbrowser
from pathlib import Path
from dotenv import load_dotenv

# ── Load config ──────────────────────────────────────────────────────────────
_env_path = os.path.expanduser("~/Documents/FRIDAY/config/.env")
if os.path.exists(_env_path):
    load_dotenv(_env_path)
else:
    load_dotenv()  # cloud: env vars already injected

# ── Logging ──────────────────────────────────────────────────────────────────
from config import DATA_DIR, LOGS_DIR, PORT, HOST
import state as _state

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "friday.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("FRIDAY")

# ── AI Clients ───────────────────────────────────────────────────────────────
from openai import OpenAI
from anthropic import Anthropic

openai_client    = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# ── Agents ────────────────────────────────────────────────────────────────────
from agents.friday_chat    import FridayChat
from agents.friday_se      import FridaySE
from agents.friday_content import FridayContent
from agents.friday_seo     import FridaySEO
from agents.friday_outreach import FridayOutreach
from agents.friday_cs      import FridayCS
from agents.friday_pm      import FridayPM
from agents.friday_image   import FridayImage
from agents.friday_invoice import FridayInvoice
from agents.friday_audit   import FridayAudit

AGENTS = {
    "FRIDAY":   FridayChat(openai_client, anthropic_client),
    "BUILD":    FridaySE(openai_client, anthropic_client),
    "CONTENT":  FridayContent(openai_client, anthropic_client),
    "SEO":      FridaySEO(openai_client, anthropic_client),
    "OUTREACH": FridayOutreach(openai_client, anthropic_client),
    "SUPPORT":  FridayCS(openai_client, anthropic_client),
    "PROJECTS": FridayPM(openai_client, anthropic_client),
    "IMAGE":    FridayImage(openai_client, anthropic_client),
    "INVOICE":  FridayInvoice(openai_client, anthropic_client),
    "AUDIT":    FridayAudit(openai_client, anthropic_client),
}

# ── Inject agents into web_app ────────────────────────────────────────────────
import web_app
web_app.agents           = AGENTS
web_app.openai_client    = openai_client
web_app.anthropic_client = anthropic_client

# ── Web server ───────────────────────────────────────────────────────────────
import uvicorn
import subprocess

WEB_PORT = PORT

def free_port(port: int):
    """Kill whatever is using the port so we can bind cleanly."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            if pid:
                subprocess.run(["kill", "-9", pid], capture_output=True)
                logger.info(f"Freed port {port} (killed pid {pid})")
    except Exception:
        pass

async def run_web():
    free_port(WEB_PORT)
    await asyncio.sleep(0.5)  # let OS release the port

    config = uvicorn.Config(
        app=web_app.app,
        host="0.0.0.0",
        port=WEB_PORT,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    try:
        await server.serve()
    except OSError as e:
        logger.error(f"Web server failed to start: {e}")
        logger.warning("Dashboard unavailable — Telegram bot still running.")

# ── Telegram bot ─────────────────────────────────────────────────────────────
import re
import json
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    filters, ContextTypes
)

from config import USAGE_FILE, OUTPUT_DIR

def track_usage(agent: str, cost: float = 0.0):
    usage = []
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE) as f:
            try: usage = json.load(f)
            except: usage = []
    usage.append({"time": datetime.now().isoformat(), "agent": agent, "cost_usd": round(cost, 5)})
    with open(USAGE_FILE, 'w') as f:
        json.dump(usage[-500:], f)

# ── Intent router ─────────────────────────────────────────────────────────────
SLASH_COMMANDS = {
    "/friday":   "FRIDAY",
    "/build":    "BUILD",
    "/se":       "BUILD",
    "/content":  "CONTENT",
    "/mkt":      "CONTENT",
    "/ads":      "CONTENT",
    "/seo":      "SEO",
    "/outreach": "OUTREACH",
    "/sales":    "OUTREACH",
    "/lead":     "OUTREACH",
    "/support":  "SUPPORT",
    "/cs":       "SUPPORT",
    "/projects": "PROJECTS",
    "/pm":       "PROJECTS",
    "/image":    "IMAGE",
    "/img":      "IMAGE",
    "/generate": "IMAGE",
    "/invoice":  "INVOICE",
    "/proposal": "INVOICE",
    "/bill":     "INVOICE",
    "/audit":    "AUDIT",
    "/check":    "AUDIT",
    "/speed":    "AUDIT",
}

CONVERSATIONAL = [
    r"^(hey|hi|hello|sup|yo|what'?s up|how are you|good morning|good night)\b",
    r"^(can you|do you|are you|will you)\b.*(hear|speak|talk|help|work|understand)",
    r"^(who are you|what are you|what'?s your name|your name)",
    r"^(thank|thanks|thx|ty)\b",
    r"^(ok|okay|cool|got it|nice|great|awesome|perfect|sounds good)",
    r"^(yes|no|sure|nah|nope|yep|yeah)\b",
]

INTENT_RULES = [
    ("BUILD", [
        r"\bbuild\b.*(site|page|app|game|tool|invite|card|flyer|form|template|website)",
        r"\b(make|create)\b.*(site|page|app|website|landing|invitation|invite|card|flyer|form|template|html|tool|calculator|menu|portfolio|banner|poster|game)\b",
        r"\b(game|snake|tetris|pong|pacman|chess|tic.tac.toe|flappy|quiz|puzzle)\b",
        r"fix\b.*(code|bug|error|html|css|js)",
        r"\b(landing page|web app|html file|invitation|digital card|flyer|template)\b",
        r"debug\b.*(code|site|app)",
        r"(digital|online)\b.*(invite|invitation|card|flyer|menu|form)",
        r"i need\b.*(page|site|form|tool|card|flyer|template|design|game)",
        r"(simple|classic|old.school|retro)\b.*(game|app|tool)",
        r"write\b.*(code|html|css|javascript|script|function)",
    ]),
    ("OUTREACH", [
        r"find\b.*(lead|prospect)",
        r"(lead|prospect)s?\s+(in|for|from)",
        r"\b(plumber|restaurant|barber|dentist|lawyer|salon|gym|clinic|shop|store)\b.+\bin\b",
        r"lead\s*gen",
        r"who (needs|want) a website",
        r"(cold\s*email|outreach|follow.?up|subject line)",
        r"send\b.*(email|to)\b.*@",
        r"(email|dm|linkedin)\b.*(template|sequence|script)",
        r"write\b.*(cold email|pitch)\b.*(business|client|prospect)",
        r"@.*\.(com|net|org|io)",
    ]),
    ("CONTENT", [
        r"(instagram|tiktok|youtube|facebook|twitter|reel|story|caption)",
        r"(content\s+(calendar|idea|plan|strategy))",
        r"(post|caption|script|hook)\b.*(social|ig|yt|tt)",
        r"(write|create)\b.*(caption|post|content|script)",
        r"hashtag",
        r"(validate|score|review|check)\b.*(ad|creative|copy)",
        r"should i (post|run) this (ad|creative)",
        r"(ad|creative)\b.*(good|work|convert|bad|trash|fire)",
    ]),
    ("SEO", [
        r"seo\b",
        r"(rank|ranking|keyword|meta|backlink)",
        r"audit\b.*(site|website|url|page)",
        r"(organic|search traffic)",
    ]),
    ("SUPPORT", [
        r"(client|customer)\b.*(said|wrote|messaged|replied|complain)",
        r"(reply|respond|draft)\b.*(client|customer|message)",
        r"(complaint|refund|unhappy|angry)\b",
        r"how (do i|should i) (respond|reply|handle)",
    ]),
    ("PROJECTS", [
        r"(project|deadline|milestone|timeline)\b",
        r"(what'?s?\s+(pending|overdue|due|next)|status update)",
        r"(track|manage)\b.*(project|work|task)",
        r"(add|create|new)\b.*(project|client)\b",
    ]),
    ("IMAGE", [
        r"(generate|create|make|design|draw)\b.*(image|graphic|logo|banner|mockup|visual|photo|illustration|thumbnail|cover|flyer|poster|background|icon|avatar)",
        r"\b(dall.?e|image\s+gen|ai\s+image|ai\s+art|midjourney.style)\b",
        r"(design|create)\b.*(social media|instagram|facebook|youtube).*(graphic|banner|post|cover|thumbnail)",
        r"generate\s+an?\s+(image|photo|visual|graphic|picture|logo)",
    ]),
    ("INVOICE", [
        r"\b(invoice|proposal|quote|estimate|bill)\b.*(client|for|send|create|make|write)",
        r"(create|make|write|generate|send)\b.*(invoice|proposal|quote|estimate)",
        r"invoice\s+for\b",
        r"send\b.*(invoice|proposal)\b.*to\b",
        r"\$\d+.*(website|design|project|service)",
    ]),
    ("AUDIT", [
        r"\baudit\b.*(site|website|url|page|https?://)",
        r"(check|analyze|test|score|grade)\b.*(site|website|url|https?://|pagespeed|speed|performance)",
        r"(how\s+fast|is\s+this\s+site|website\s+speed|site\s+speed|core\s+web\s+vitals|lighthouse)",
        r"https?://\S+",  # Any bare URL → try to audit it
    ]),
]

def detect_intent(text: str) -> str | None:
    t = text.lower().strip()
    # Short or conversational messages always go to FRIDAY brain
    if len(t) < 15:
        return None
    for pattern in CONVERSATIONAL:
        if re.search(pattern, t):
            return None  # let FRIDAY handle it
    for agent_key, patterns in INTENT_RULES:
        for pattern in patterns:
            if re.search(pattern, t):
                return agent_key
    return None


VOICE_REQUEST  = re.compile(r"\b(speak|voice|audio|say it|tell me|read it|out loud|no text|don'?t type)\b", re.I)
TEXT_REQUEST   = re.compile(r"\b(text only|no voice|no audio|write it|type it|don'?t speak)\b", re.I)

ELEVENLABS_KEY      = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "EXAVITQu4vr4xnSDxMaL")


async def transcribe_voice(file_path: str) -> str:
    """Transcribe a voice file using OpenAI Whisper."""
    with open(file_path, "rb") as f:
        result = await asyncio.to_thread(
            openai_client.audio.transcriptions.create,
            model="whisper-1",
            file=f
        )
    return result.text


def tts_elevenlabs(text: str) -> bytes | None:
    """Convert text to speech via ElevenLabs, return mp3 bytes."""
    import re as _re
    text = _re.sub(r'\*+', '', text)
    text = _re.sub(r'#{1,6}\s', '', text)
    text = _re.sub(r'`+', '', text)
    text = _re.sub(r'\n+', ' ', text)
    text = text[:600]
    if not ELEVENLABS_KEY:
        return None
    try:
        resp = __import__('requests').post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
            headers={"xi-api-key": ELEVENLABS_KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"},
            json={"text": text, "voice_settings": {"stability": 0.45, "similarity_boost": 0.80}},
            timeout=20
        )
        if "audio" in resp.headers.get("content-type", ""):
            return resp.content
    except Exception as e:
        logger.error(f"TTS error: {e}")
    return None


async def send_voice_reply(update, response: str):
    """Send response as a Telegram voice message."""
    import tempfile
    audio = await asyncio.to_thread(tts_elevenlabs, response)
    if not audio:
        await update.message.reply_text(response)
        return
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(audio)
        tmp_path = f.name
    try:
        with open(tmp_path, "rb") as f:
            await update.message.reply_voice(voice=f)
    except Exception as e:
        logger.error(f"Voice reply failed: {e}")
        await update.message.reply_text(response)
    finally:
        os.unlink(tmp_path)


async def send_response(update, response: str, use_voice: bool = False):
    if use_voice:
        await send_voice_reply(update, response)
        return
    if len(response) <= 4096:
        await update.message.reply_text(response)
    else:
        for i in range(0, len(response), 3800):
            await update.message.reply_text(response[i:i+3800])


async def process_message(update, context, text: str, use_voice: bool = False):
    """Core message processing — shared by text and voice handlers."""
    if text.lower() in ("status", "/status", "/credits"):
        await status_cmd(update, context)
        return

    agent_key = None
    message = text
    for cmd, key in SLASH_COMMANDS.items():
        if text.lower().startswith(cmd):
            agent_key = key
            message = text[len(cmd):].strip() or "What can you help me with?"
            break

    if not agent_key:
        agent_key = detect_intent(text)
    if not agent_key:
        agent_key = "FRIDAY"

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="record_voice" if use_voice else "typing"
    )
    logger.info(f"→ {agent_key} {'🔊' if use_voice else '💬'}: {text[:80]}")
    track_usage(agent_key)

    uid      = str(update.effective_user.id) if update and update.effective_user else "tg"
    history  = _state.get_history(uid)
    response = await AGENTS[agent_key].handle(message, update, history=history)

    # ── Extract file markers from response ─────────────────────────────────
    spreadsheet_path = None
    image_path       = None
    invoice_path     = None

    for marker_pattern, var_name in [
        (r'\[SPREADSHEET:(.+?)\|(.+?)\]', 'spreadsheet'),
        (r'\[IMAGE:(.+?)\|(.+?)\]',       'image'),
        (r'\[INVOICE:(.+?)\|(.+?)\]',     'invoice'),
    ]:
        m = re.search(marker_pattern, response)
        if m:
            fpath    = m.group(1)
            response = response[:m.start()].rstrip()
            if var_name == 'spreadsheet': spreadsheet_path = fpath
            elif var_name == 'image':     image_path       = fpath
            elif var_name == 'invoice':   invoice_path     = fpath

    _state.append_history(uid, "user",      message)
    _state.append_history(uid, "assistant", response[:500])

    await send_response(update, response, use_voice=use_voice)

    # ── Send spreadsheet ────────────────────────────────────────────────────
    if spreadsheet_path and os.path.exists(spreadsheet_path):
        try:
            with open(spreadsheet_path, "rb") as f:
                fname = os.path.basename(spreadsheet_path)
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=fname,
                    caption=f"Your leads spreadsheet — {fname}",
                )
        except Exception as e:
            logger.error(f"Failed to send spreadsheet via Telegram: {e}")

    # ── Send image ──────────────────────────────────────────────────────────
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, "rb") as f:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=f,
                    caption=f"Generated image — {os.path.basename(image_path)}",
                )
        except Exception as e:
            logger.error(f"Failed to send image via Telegram: {e}")

    # ── Send invoice / proposal ─────────────────────────────────────────────
    if invoice_path and os.path.exists(invoice_path):
        try:
            with open(invoice_path, "rb") as f:
                fname = os.path.basename(invoice_path)
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=f,
                    filename=fname,
                    caption=f"{'Invoice' if 'invoice' in fname else 'Proposal'} — {fname}",
                )
        except Exception as e:
            logger.error(f"Failed to send invoice via Telegram: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Detect if user wants voice or text response
    if TEXT_REQUEST.search(text):
        use_voice = False
    elif VOICE_REQUEST.search(text):
        use_voice = True
    else:
        use_voice = False  # text in → text out by default

    await process_message(update, context, text, use_voice=use_voice)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User sent a voice message — transcribe and reply with voice."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            await voice_file.download_to_drive(f.name)
            tmp_path = f.name

        text = await transcribe_voice(tmp_path)
        os.unlink(tmp_path)

        if not text.strip():
            await update.message.reply_text("Couldn't hear that clearly, Boss. Try again.")
            return

        logger.info(f"🎤 Transcribed: {text[:80]}")

        # Check if user explicitly wants text back
        use_voice = not bool(TEXT_REQUEST.search(text))
        await process_message(update, context, text, use_voice=use_voice)

    except Exception as e:
        logger.error(f"Voice handler error: {e}")
        await update.message.reply_text("Had trouble processing that voice message, Boss.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    photo     = update.message.photo[-1]
    file      = await context.bot.get_file(photo.file_id)
    image_url = file.file_path
    caption   = update.message.caption or "Validate this ad and tell me if I should post it."
    response  = await AGENTS["CONTENT"].handle(caption, update, image_url=image_url)
    await send_response(update, response)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "FRIDAY online. All systems operational.\n\n"
        "Just talk — I'll route it automatically.\n\n"
        "BUILD    — sites, games, tools, invitations\n"
        "OUTREACH — find leads, write & send cold emails\n"
        "CONTENT  — social posts, captions, validate ads\n"
        "SEO      — keywords, on-page optimization\n"
        "SUPPORT  — draft replies to client messages\n"
        "PROJECTS — track deadlines and progress\n"
        "IMAGE    — generate graphics & mockups (DALL-E 3)\n"
        "INVOICE  — create invoices & proposals\n"
        "AUDIT    — full website speed + SEO audit\n\n"
        "/build /outreach /content /seo /support /projects\n"
        "/image /invoice /audit\n\n"
        "Web dashboard: http://localhost:7771\n\n"
        "What are we doing, Boss?"
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_cost = 0.0
    total_calls = 0
    agent_counts = {}

    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE) as f:
            try:
                usage = json.load(f)
                total_calls = len(usage)
                for u in usage:
                    total_cost += u.get("cost_usd", 0)
                    a = u.get("agent", "unknown")
                    agent_counts[a] = agent_counts.get(a, 0) + 1
            except: pass

    projects = len(os.listdir(OUTPUT_DIR)) if os.path.exists(OUTPUT_DIR) else 0
    top = sorted(agent_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_str = "\n".join([f"  {a}: {c} calls" for a, c in top]) or "  No activity yet"

    await update.message.reply_text(
        f"FRIDAY STATUS\n\n"
        f"Projects built: {projects}\n"
        f"API calls: {total_calls}\n"
        f"Est. cost: ${total_cost:.4f}\n\n"
        f"Top modules:\n{top_str}\n\n"
        f"Dashboard: http://localhost:7771\n"
        f"Full billing: platform.openai.com/usage"
    )


async def run_telegram():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN missing from .env — Telegram disabled")
        return

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("help",    start))
    app.add_handler(CommandHandler("status",  status_cmd))
    app.add_handler(CommandHandler("credits", status_cmd))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Telegram bot started.")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    # ── Follow-up reminder loop ───────────────────────────────────────────────
    owner_chat_id = os.getenv("TELEGRAM_OWNER_ID", "")

    async def followup_loop():
        """Check for due follow-ups every hour and ping the owner."""
        if not owner_chat_id:
            return
        while True:
            await asyncio.sleep(3600)   # check every hour
            try:
                due = _state.get_followups_due()
                if not due:
                    continue
                names = ", ".join(l["name"] for l in due[:5])
                extra = f" (+{len(due)-5} more)" if len(due) > 5 else ""
                msg   = (
                    f"Follow-up reminder, Boss.\n\n"
                    f"{len(due)} lead{'s' if len(due)>1 else ''} waiting:\n"
                    f"{names}{extra}\n\n"
                    f"Say 'show pipeline' in OUTREACH to see the full list."
                )
                await app.bot.send_message(chat_id=owner_chat_id, text=msg)
            except Exception as e:
                logger.warning(f"Follow-up loop error: {e}")

    asyncio.create_task(followup_loop())

    # Keep running until cancelled
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


# ── Entry point ───────────────────────────────────────────────────────────────
async def main():
    print("\n" + "="*50)
    print("  FRIDAY — AI Assistant")
    print("  FileFlow Inc.")
    print("="*50)
    print(f"\n  Dashboard  →  http://localhost:7771")
    print(f"  Telegram   →  active")
    print(f"  Agents     →  {len(AGENTS)} loaded")
    print("\n  FRIDAY is online. Press Ctrl+C to stop.\n")

    # Only open browser when running manually (not under pm2)
    async def open_browser():
        if not os.getenv("PM2_HOME"):
            await asyncio.sleep(1.5)
            webbrowser.open("http://localhost:7771")

    await asyncio.gather(
        run_web(),
        run_telegram(),
        open_browser(),
        return_exceptions=True,  # one failing task won't kill the others
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nFRIDAY offline. See you, Boss.\n")
