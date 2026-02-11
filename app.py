import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ContextTypes, MessageHandler, CommandHandler, CallbackQueryHandler, filters

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
DRAFTS_FILE = DATA_DIR / "drafts.json"
pending_users: set[int] = set()
threads: list[dict] = []
# Store draft messages with their states
# Format: {user_id: {"message": "text", "message_id": int, "target_user_id": int, "is_editing": bool}}
draft_messages: dict[int, dict] = {}


def load_threads() -> None:
    global threads
    try:
        threads = json.loads(THREADS_FILE.read_text(encoding="utf-8"))
        if not isinstance(threads, list):
            threads = []
    except Exception:
        threads = []


def load_drafts() -> None:
    global draft_messages
    try:
        draft_messages = json.loads(DRAFTS_FILE.read_text(encoding="utf-8"))
        if not isinstance(draft_messages, dict):
            draft_messages = {}
    except Exception:
        draft_messages = {}


def save_draft(user_id: int, draft_data: dict) -> None:
    draft_messages[user_id] = draft_data
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        DRAFTS_FILE.write_text(json.dumps(draft_messages), encoding="utf-8")
    except Exception as e:
        print("Failed to save draft:", e)


def remove_draft(user_id: int) -> None:
    if user_id in draft_messages:
        del draft_messages[user_id]
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            DRAFTS_FILE.write_text(json.dumps(draft_messages), encoding="utf-8")
        except Exception as e:
            print("Failed to remove draft:", e)


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
load_drafts()


def create_send_edit_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Create inline keyboard with Send and Edit buttons."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Send", callback_data=f"send_{user_id}"),
            InlineKeyboardButton("✏️ Edit", callback_data=f"edit_{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


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

    # Check if this is an edit message first
    admin_user_id = msg.from_user.id
    if (msg.reply_to_message and 
        admin_user_id in draft_messages and 
        draft_messages[admin_user_id].get("is_editing", False)):
        await on_edit_message(update, context)
        return

    # Reply in group: only in configured group, only to bot's messages
    if msg.reply_to_message:
        if str(msg.chat_id) != GROUP_ID:
            return
        if not (msg.reply_to_message.from_user and msg.reply_to_message.from_user.is_bot):
            return
        user_chat_id = await resolve_user_chat_id(msg.reply_to_message)
        if user_chat_id is not None:
            # Send message with Send/Edit buttons to the admin who replied
            admin_user_id = msg.from_user.id
            keyboard = create_send_edit_keyboard(user_chat_id)
            
            # Store the draft message
            draft_data = {
                "message": msg.text,
                "target_user_id": user_chat_id,
                "is_editing": False
            }
            save_draft(admin_user_id, draft_data)
            
            # Send the message with buttons to the admin
            sent_msg = await context.bot.send_message(
                chat_id=admin_user_id, 
                text=f"📝 **Draft Reply:**\n\n{msg.text}\n\n👆 Choose an action:", 
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
            # Update draft with message_id for editing
            draft_data["message_id"] = sent_msg.message_id
            save_draft(admin_user_id, draft_data)
            
            log.info("DRAFT_CREATED admin=%s target_user=%s text=%s", admin_user_id, user_chat_id, (msg.text[:50] + "…") if len(msg.text) > 50 else msg.text)
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
        log.info("MESSAGE_SENT user_id=%s name=%s forwarded_to_group group_message_id=%s", msg.chat_id, full_name, group_message_id)
    except Exception as e:
        log.exception("Failed to send message to group: %s", e)
        await context.bot.send_message(
            msg.chat_id, "Couldn't reach the admins right now. Please try again in a moment."
        )
        return

    if group_message_id is None:
        log.error("Send to group returned no message id")
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


async def on_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from Send/Edit buttons."""
    query = update.callback_query
    await query.answer()
    
    if not query.data:
        return
    
    admin_user_id = query.from_user.id
    
    # Check if admin has a draft
    if admin_user_id not in draft_messages:
        await query.edit_message_text("❌ No draft found. Please reply to a user message first.")
        return
    
    draft_data = draft_messages[admin_user_id]
    
    if query.data.startswith("send_"):
        # Send the message to the user
        target_user_id = draft_data["target_user_id"]
        message_text = draft_data["message"]
        
        try:
            await context.bot.send_message(chat_id=target_user_id, text=message_text)
            pending_users.discard(target_user_id)
            
            # Update the admin's message to show it was sent
            await query.edit_message_text(
                f"✅ **Message Sent Successfully!**\n\n{message_text}",
                parse_mode="Markdown"
            )
            
            # Remove the draft
            remove_draft(admin_user_id)
            
            log.info("MESSAGE_SENT admin=%s to_user=%s text=%s", admin_user_id, target_user_id, (message_text[:50] + "…") if len(message_text) > 50 else message_text)
            
        except Exception as e:
            log.exception("Failed to send message to user: %s", e)
            await query.edit_message_text(
                f"❌ **Failed to send message.**\n\nError: {str(e)}\n\nPlease try again.",
                parse_mode="Markdown"
            )
    
    elif query.data.startswith("edit_"):
        # Enter edit mode
        draft_data["is_editing"] = True
        save_draft(admin_user_id, draft_data)
        
        await query.edit_message_text(
            f"✏️ **Edit Mode**\n\nCurrent message:\n{draft_data['message']}\n\n📝 Send your edited message as a reply to this message.",
            parse_mode="Markdown"
        )


async def on_edit_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle edited messages when user is in edit mode."""
    msg = update.message
    if not msg or not msg.text:
        return
    
    admin_user_id = msg.from_user.id
    
    # Check if this is a reply to our edit message and user is in edit mode
    if (msg.reply_to_message and 
        admin_user_id in draft_messages and 
        draft_messages[admin_user_id].get("is_editing", False)):
        
        # Update the draft with the new message
        draft_data = draft_messages[admin_user_id]
        draft_data["message"] = msg.text
        draft_data["is_editing"] = False
        save_draft(admin_user_id, draft_data)
        
        # Create new keyboard and update the message
        keyboard = create_send_edit_keyboard(draft_data["target_user_id"])
        
        try:
            # Edit the original message with the new content
            await context.bot.edit_message_text(
                chat_id=admin_user_id,
                message_id=draft_data["message_id"],
                text=f"📝 **Updated Draft Reply:**\n\n{msg.text}\n\n👆 Choose an action:",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            
            # Delete the user's edit message to keep chat clean
            await msg.delete()
            
            log.info("DRAFT_UPDATED admin=%s new_text=%s", admin_user_id, (msg.text[:50] + "…") if len(msg.text) > 50 else msg.text)
            
        except Exception as e:
            log.exception("Failed to update draft: %s", e)
            await msg.reply_text("❌ Failed to update draft. Please try again.")


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
    app.add_handler(CallbackQueryHandler(on_callback_query))
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
