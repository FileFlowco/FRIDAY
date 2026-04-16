#!/usr/bin/env python3
"""
FRIDAY - AI Agent System
"""

import os
import re
import json
import logging
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, CommandHandler,
    filters, ContextTypes
)
from openai import OpenAI
from anthropic import Anthropic

# Load .env
load_dotenv(os.path.expanduser("~/Documents/FRIDAY/config/.env"))

# Logging
os.makedirs(os.path.expanduser("~/Documents/FRIDAY/logs"), exist_ok=True)
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.expanduser("~/Documents/FRIDAY/logs/friday.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Both AI clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Usage tracking
USAGE_FILE = os.path.expanduser("~/Documents/FRIDAY/logs/usage.json")

def track_usage(agent: str, cost: float):
    usage = []
    if os.path.exists(USAGE_FILE):
        with open(USAGE_FILE) as f:
            try: usage = json.load(f)
            except: usage = []
    usage.append({"time": datetime.now().isoformat(), "agent": agent, "cost_usd": round(cost, 5)})
    with open(USAGE_FILE, 'w') as f:
        json.dump(usage[-500:], f)

# Import agents
from agents.friday_chat import FridayChat         # General brain — handles anything, has memory
from agents.friday_se import FridaySE             # Builds websites, games, tools, invitations
from agents.friday_content import FridayContent   # Social posts + ad validation
from agents.friday_seo import FridaySEO           # SEO audits & rankings
from agents.friday_outreach import FridayOutreach # Leads + cold emails
from agents.friday_cs import FridayCS             # Client support
from agents.friday_pm import FridayPM             # Project tracking

AGENTS = {
    "FRIDAY":   FridayChat(openai_client, anthropic_client),
    "BUILD":    FridaySE(openai_client, anthropic_client),
    "CONTENT":  FridayContent(openai_client, anthropic_client),
    "SEO":      FridaySEO(openai_client, anthropic_client),
    "OUTREACH": FridayOutreach(openai_client, anthropic_client),
    "SUPPORT":  FridayCS(openai_client, anthropic_client),
    "PROJECTS": FridayPM(openai_client, anthropic_client),
}

# Slash commands — intuitive names
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
}

# ── Smart intent router ──────────────────────────────────────────────────────
# Keyword signals for each agent — first match wins (ordered by specificity)

INTENT_RULES = [
    # BUILD — builds anything: sites, games, invitations, tools, anything coded
    ("BUILD", [
        r"build\b",
        r"\b(game|snake|tetris|pong|pacman|chess|tic.tac.toe|flappy|quiz|puzzle)\b",
        r"(make|create|design|generate|code|write)\b.*(site|page|app|website|landing|invitation|invite|card|flyer|form|template|html|tool|calculator|menu|portfolio|banner|poster|game)",
        r"fix\b.*(code|bug|error|html|css|js)",
        r"(website|landing page|web app|html|invitation|digital card|flyer|template)\b",
        r"debug\b",
        r"(digital|online)\b.*(invite|invitation|card|flyer|menu|form)",
        r"(invite|invitation)\b",
        r"i need\b.*(page|site|form|tool|card|flyer|template|design|game)",
        r"(simple|classic|old.school|retro)\b.*(game|app|tool)",
    ]),
    # OUTREACH — leads + cold email only (tight, specific triggers)
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
    # CONTENT — social posts + ad validation (merged MKT + ADS)
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
    # SEO — search rankings
    ("SEO", [
        r"seo\b",
        r"(rank|ranking|keyword|meta|backlink)",
        r"audit\b.*(site|website|url|page)",
        r"(organic|search traffic)",
    ]),
    # SUPPORT — client replies
    ("SUPPORT", [
        r"(client|customer)\b.*(said|wrote|messaged|replied|complain)",
        r"(reply|respond|draft)\b.*(client|customer|message)",
        r"(complaint|refund|unhappy|angry)\b",
        r"how (do i|should i) (respond|reply|handle)",
    ]),
    # PROJECTS — project tracking
    ("PROJECTS", [
        r"(project|deadline|milestone|timeline)\b",
        r"(what'?s?\s+(pending|overdue|due|next)|status update)",
        r"(track|manage)\b.*(project|work|task)",
        r"(add|create|new)\b.*(project|client)\b",
    ]),
]

def detect_intent(text: str) -> str | None:
    """Return agent key based on message content, or None if unclear."""
    t = text.lower()
    for agent_key, patterns in INTENT_RULES:
        for pattern in patterns:
            if re.search(pattern, t):
                return agent_key
    return None


async def send_response(update, response: str):
    """Send response, split if too long. No headers, no keyboard."""
    if len(response) <= 4096:
        await update.message.reply_text(response)
    else:
        for i in range(0, len(response), 3800):
            await update.message.reply_text(response[i:i+3800])


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    text_lower = text.lower()

    # /status command
    if text_lower in ("status", "/status", "/credits"):
        await status_cmd(update, context)
        return

    # Force a specific agent via slash command
    agent_key = None
    message = text
    for cmd, key in SLASH_COMMANDS.items():
        if text_lower.startswith(cmd):
            agent_key = key
            message = text[len(cmd):].strip() or "What can you help me with?"
            break

    # Auto-detect intent if no slash command
    if not agent_key:
        agent_key = detect_intent(text)

    # Default fallback — FRIDAY general brain handles anything conversational
    if not agent_key:
        agent_key = "FRIDAY"

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    logger.info(f"→ {agent_key}: {text[:80]}")

    # Load conversation history (last 10 exchanges)
    history = context.user_data.get("history", [])

    agent = AGENTS[agent_key]
    response = await agent.handle(message, update, history=history)

    # Save to history
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": response[:500]})  # trim long responses
    context.user_data["history"] = history[-20:]  # keep last 20 messages (10 exchanges)

    await send_response(update, response)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Photos go to CONTENT for ad validation."""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_url = file.file_path
    caption = update.message.caption or "Validate this ad and tell me if I should post it."
    response = await AGENTS["CONTENT"].handle(caption, update, image_url=image_url)  # GPT-4o vision
    await send_response(update, response)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "FRIDAY online. All systems operational.\n\n"
        "Just talk — I'll route it. No buttons, no menus.\n\n"
        "BUILD — websites, games, tools, invitations, anything\n"
        "OUTREACH — find leads, write & send cold emails\n"
        "CONTENT — social posts, captions, validate ads\n"
        "SEO — audit sites, keywords, rankings\n"
        "SUPPORT — draft replies to client messages\n"
        "PROJECTS — track deadlines and progress\n\n"
        "Or force a mode: /build /outreach /content /seo /support /projects\n\n"
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

    output_dir = os.path.expanduser("~/Documents/FRIDAY/output")
    projects = len(os.listdir(output_dir)) if os.path.exists(output_dir) else 0
    top = sorted(agent_counts.items(), key=lambda x: x[1], reverse=True)[:3]
    top_str = "\n".join([f"  {a}: {c} calls" for a, c in top]) or "  No activity yet"

    await update.message.reply_text(
        f"FRIDAY STATUS\n\n"
        f"Projects built: {projects}\n"
        f"API calls: {total_calls}\n"
        f"Est. cost: ${total_cost:.4f}\n\n"
        f"Top modules:\n{top_str}\n\n"
        f"Full billing: platform.openai.com/usage"
    )


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN missing from .env")

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("credits", status_cmd))
    for cmd in SLASH_COMMANDS:
        pass  # handled inside handle_text via prefix matching
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("\nFRIDAY is online.")
    logger.info("FRIDAY started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
