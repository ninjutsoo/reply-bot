import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, filters

load_dotenv()

# Config
BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROUP_ID = (os.environ.get("GROUP_ID") or "").strip()
PORT = os.environ.get("PORT")
WEBHOOK_BASE_URL = os.environ.get("WEBHOOK_BASE_URL")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET") or "reply-bot-webhook"

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is required")
if not GROUP_ID:
    raise SystemExit("GROUP_ID is required (add bot to group, then get id from getUpdates)")

USE_WEBHOOK = bool(PORT and WEBHOOK_BASE_URL)

WELCOME_MESSAGE = os.environ.get(
    "WELCOME_MESSAGE",
    "Send your message in one message. Our admins will receive it and reply to you here.",
)
MESSAGE_AFTER = os.environ.get("MESSAGE_AFTER", "We'll get back to you as soon as we can.")
WAITING_MESSAGE = os.environ.get(
    "WAITING_MESSAGE",
    "Waiting for admins to reply. You can only send another message after they've replied to your previous message.",
)

# Local file store for message threads
DATA_DIR = Path(os.getcwd()) / "data"
THREADS_FILE = DATA_DIR / "threads.json"
pending_users: set[int] = set()
threads: list[dict] = []


def load_threads() -> None:
    global threads
    try:
        threads = json.loads(THREADS_FILE.read_text(encoding="utf-8"))
        if not isinstance(threads, list):
            threads = []
    except Exception:
        threads = []


def save_thread(row: dict) -> None:
    threads.append(row)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        THREADS_FILE.write_text(json.dumps(threads), encoding="utf-8")
    except Exception as e:
        print("Failed to save thread:", e)


def find_user_by_group_message(group_chat_id: str, group_message_id: int) -> int | None:
    for t in threads:
        if t.get("group_chat_id") == group_chat_id and t.get("group_message_id") == group_message_id:
            return t.get("user_chat_id")
    return None


load_threads()


async def resolve_user_chat_id(reply_to_message) -> int | None:
    if not reply_to_message or not getattr(reply_to_message, "message_id", None):
        return None
    mid = reply_to_message.message_id
    from_file = find_user_by_group_message(GROUP_ID, mid)
    if from_file is not None:
        return from_file
    text = getattr(reply_to_message, "text", None) or ""
    match = re.search(r"User\s*<(-?\d+)>", text)
    return int(match.group(1)) if match else None


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.message
    if not msg or not msg.text:
        return

    # Reply in group: only in configured group, only to bot's messages
    if msg.reply_to_message:
        if str(msg.chat_id) != GROUP_ID:
            return
        if not (msg.reply_to_message.from_user and msg.reply_to_message.from_user.is_bot):
            return
        user_chat_id = await resolve_user_chat_id(msg.reply_to_message)
        if user_chat_id is not None:
            await context.bot.send_message(chat_id=user_chat_id, text=msg.text)
            pending_users.discard(user_chat_id)
        return

    # Only forward when user messages in private
    if msg.chat.type != "private":
        return

    if msg.from_user.id in pending_users:
        await msg.reply_text(WAITING_MESSAGE)
        return

    from_user = msg.from_user
    full_name = " ".join(filter(None, [from_user.first_name, from_user.last_name])) or "Unknown"
    handle = f" (@{from_user.username})" if from_user.username else ""
    user_line = f"User: {full_name}{handle}\n\n{msg.text}"

    await context.bot.send_message(chat_id=msg.chat_id, text=MESSAGE_AFTER)

    try:
        sent = await context.bot.send_message(chat_id=GROUP_ID, text=user_line)
        group_message_id = sent.message_id
    except Exception as e:
        print("Failed to send message to group:", e)
        await context.bot.send_message(
            msg.chat_id, "Couldn't reach the admins right now. Please try again in a moment."
        )
        return

    if group_message_id is None:
        print("Send to group returned no message id")
        await context.bot.send_message(
            msg.chat_id, "Couldn't reach the admins right now. Please try again in a moment."
        )
        return

    row = {
        "group_chat_id": GROUP_ID,
        "group_message_id": group_message_id,
        "user_chat_id": msg.chat_id,
    }
    save_thread(row)
    pending_users.add(msg.chat_id)


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(WELCOME_MESSAGE)


def main() -> None:
    import asyncio
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    if USE_WEBHOOK:
        base = WEBHOOK_BASE_URL.rstrip("/")
        url = f"{base}/{WEBHOOK_SECRET}"
        asyncio.run(_run_webhook(app, int(PORT), WEBHOOK_SECRET, url))
    else:
        app.run_polling()


async def _run_webhook(application: Application, port: int, path: str, webhook_url: str) -> None:
    import asyncio
    from aiohttp import web
    await application.bot.set_webhook(webhook_url)

    async def telegram_post(request: web.Request) -> web.Response:
        try:
            data = await request.json()
            update = Update.de_json(data, application.bot)
            await application.update_queue.put(update)
        except Exception as e:
            print("Webhook error:", e)
        return web.Response(status=200)

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True, "bot": "reply-bot"})

    app_web = web.Application()
    app_web.router.add_post(f"/{path}", telegram_post)
    app_web.router.add_get("/health", health)
    runner = web.AppRunner(app_web)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print("Webhook set:", webhook_url)
    print("Server listening on port", port)
    async with application:
        await application.start()
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    main()
