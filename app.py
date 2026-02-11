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
# Format: {user_chat_id: {"text": str, "preview_message_id": int, "is_editing": bool}}
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
        raw = json.loads(DRAFTS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            draft_messages = {}
            return
        # JSON object keys are strings; convert to ints where possible
        fixed: dict[int, dict] = {}
        for k, v in raw.items():
            try:
                ik = int(k)
            except Exception:
                continue
            if isinstance(v, dict):
                fixed[ik] = v
        draft_messages = fixed
    except Exception:
        draft_messages = {}


def save_draft(user_id: int, draft_data: dict) -> None:
    uid = int(user_id)
    draft_messages[uid] = draft_data
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        # Ensure keys persist as strings for JSON
        to_save = {str(k): v for k, v in draft_messages.items()}
        DRAFTS_FILE.write_text(json.dumps(to_save), encoding="utf-8")
    except Exception as e:
        print("Failed to save draft:", e)


def remove_draft(user_id: int) -> None:
    uid = int(user_id)
    if uid in draft_messages:
        del draft_messages[uid]
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            to_save = {str(k): v for k, v in draft_messages.items()}
            DRAFTS_FILE.write_text(json.dumps(to_save), encoding="utf-8")
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
            InlineKeyboardButton("Send", callback_data=f"send_{user_id}"),
            InlineKeyboardButton("Edit", callback_data=f"edit_{user_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def format_user_line(user_chat_id: int, full_name: str, username: str | None, text: str) -> str:
    handle = f" (@{username})" if username else ""
    return f"{full_name}{handle}\n\n{text}"


async def _delete_message_later(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    delay_seconds: int,
) -> None:
    async def _job_cb(ctx: ContextTypes.DEFAULT_TYPE) -> None:
        data = ctx.job.data or {}
        try:
            await ctx.bot.delete_message(chat_id=data["chat_id"], message_id=data["message_id"])
        except Exception:
            return

    try:
        context.job_queue.run_once(
            _job_cb,
            delay_seconds,
            data={"chat_id": chat_id, "message_id": message_id},
            name=f"del:{chat_id}:{message_id}",
        )
    except Exception:
        return


async def _send_ephemeral(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    delay_seconds: int = 8,
) -> None:
    try:
        m = await context.bot.send_message(chat_id=chat_id, text=text)
        await _delete_message_later(context, chat_id, m.message_id, delay_seconds)
    except Exception:
        return


async def _update_user_preview(
    context: ContextTypes.DEFAULT_TYPE,
    user_chat_id: int,
    preview_message_id: int,
    text: str,
) -> None:
    keyboard = create_send_edit_keyboard(user_chat_id)
    await context.bot.edit_message_text(
        chat_id=user_chat_id,
        message_id=preview_message_id,
        text=text,
        reply_markup=keyboard,
    )


async def on_edited_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    When the user edits their message using Telegram's native Edit UI,
    automatically update the bot's draft preview (and keep Send/Edit buttons).
    """
    msg = update.edited_message
    if not msg or not msg.text:
        return
    if msg.chat.type != "private":
        return

    user_chat_id = msg.chat_id
    draft = draft_messages.get(user_chat_id)
    if not draft:
        return

    origin_id = draft.get("origin_message_id")
    if origin_id != msg.message_id:
        return

    # Update draft + preview
    from_user = msg.from_user
    full_name = " ".join(filter(None, [from_user.first_name, from_user.last_name])) or "Unknown" if from_user else "Unknown"
    username = from_user.username if from_user else None

    draft["text"] = msg.text
    draft["user_line"] = format_user_line(user_chat_id, full_name, username, msg.text)
    save_draft(user_chat_id, draft)

    preview_message_id = draft.get("preview_message_id")
    if isinstance(preview_message_id, int):
        try:
            await _update_user_preview(context, user_chat_id, preview_message_id, msg.text)
        except Exception as e:
            log.exception("Failed to update draft preview after edit: %s", e)


async def resolve_user_chat_id(reply_to_message) -> int | None:
    if not reply_to_message or not getattr(reply_to_message, "message_id", None):
        return None
    mid = reply_to_message.message_id
    from_file = find_user_by_group_message(GROUP_ID, mid)
    if from_file is not None:
        return from_file
    # No reliable fallback parsing since we don't include user IDs in the group message text.
    return None


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
            # Direct reply to user (old behavior - send immediately)
            await context.bot.send_message(chat_id=user_chat_id, text=msg.text)
            pending_users.discard(user_chat_id)
            log.info("REPLY_BACK to_user=%s text=%s", user_chat_id, (msg.text[:50] + "…") if len(msg.text) > 50 else msg.text)
        return

    # Only forward when user messages in private
    if msg.chat.type != "private":
        return

    user_chat_id = msg.chat_id

    if msg.from_user.id in pending_users:
        # Keep chat clean: auto-delete the bot notice.
        await _send_ephemeral(context, user_chat_id, WAITING_MESSAGE, delay_seconds=8)
        return

    from_user = msg.from_user
    full_name = " ".join(filter(None, [from_user.first_name, from_user.last_name])) or "Unknown"
    user_line = format_user_line(user_chat_id, full_name, from_user.username, msg.text)

    # Draft flow: buttons appear in the user's chat with the bot.
    existing = draft_messages.get(user_chat_id)
    keyboard = create_send_edit_keyboard(user_chat_id)

    # If user already has a draft preview, update it; otherwise create a new preview message.
    if existing and isinstance(existing.get("preview_message_id"), int):
        existing["text"] = msg.text
        existing["user_line"] = user_line
        existing["origin_message_id"] = msg.message_id
        save_draft(user_chat_id, existing)
        try:
            await _update_user_preview(context, user_chat_id, existing["preview_message_id"], msg.text)
        except Exception as e:
            log.exception("Failed to update draft preview: %s", e)
        return

    try:
        preview = await context.bot.send_message(
            chat_id=user_chat_id,
            text=msg.text,
            reply_markup=keyboard,
            reply_to_message_id=msg.message_id,
        )
        save_draft(
            user_chat_id,
            {
                "text": msg.text,
                "user_line": user_line,
                "preview_message_id": preview.message_id,
                "origin_message_id": msg.message_id,
            },
        )
        log.info(
            "DRAFT_CREATED user_id=%s name=%s",
            user_chat_id,
            full_name,
        )
    except Exception as e:
        log.exception("Failed to create draft preview: %s", e)
        await context.bot.send_message(user_chat_id, "Couldn't create a draft right now. Please try again.")
        return


async def on_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries from Send/Edit buttons."""
    query = update.callback_query
    await query.answer()
    
    if not query.data:
        return

    # Buttons must only work in private chat with the user.
    if not query.message or query.message.chat.type != "private":
        return

    if not (query.data.startswith("send_") or query.data.startswith("edit_")):
        await query.edit_message_text("Invalid button data.")
        return

    try:
        user_chat_id = int(query.data.split("_", 1)[1])
    except Exception:
        await query.edit_message_text("Invalid button data.")
        return

    # Ensure only the same user can use their buttons
    if query.from_user.id != user_chat_id:
        return

    draft = draft_messages.get(user_chat_id)
    if not draft:
        await query.edit_message_text("No draft found. Send a message to create one.")
        return

    if query.data.startswith("edit_"):
        # Bots cannot open Telegram's native edit UI. Instead, instruct the user to edit
        # their last message using Telegram's built-in Edit action; we'll auto-update preview.
        note = (
            "To edit using Telegram:\n"
            "1. Tap and hold your last message\n"
            "2. Tap Edit\n"
            "3. Change the text and save\n\n"
            "The preview above will update automatically."
        )
        try:
            # Edit the preview message itself (no extra clutter).
            await context.bot.edit_message_text(
                chat_id=user_chat_id,
                message_id=query.message.message_id,
                text=note,
                reply_markup=create_send_edit_keyboard(user_chat_id),
            )
        except Exception:
            await _send_ephemeral(context, user_chat_id, note, delay_seconds=12)
        return

    # Send pressed: forward to group (no buttons in group)
    try:
        user_line = draft.get("user_line") or draft.get("text") or ""
        sent = await context.bot.send_message(chat_id=GROUP_ID, text=user_line)
        group_message_id = sent.message_id

        row = {"group_chat_id": GROUP_ID, "group_message_id": group_message_id, "user_chat_id": user_chat_id}
        save_thread(row)
        pending_users.add(user_chat_id)

        # Keep chat clean: delete the bot preview message. User's original message remains.
        try:
            await context.bot.delete_message(chat_id=user_chat_id, message_id=query.message.message_id)
        except Exception:
            try:
                await query.edit_message_text("Sent.")
                await _delete_message_later(context, user_chat_id, query.message.message_id, delay_seconds=6)
            except Exception:
                pass
        remove_draft(user_chat_id)
        log.info("MESSAGE_SENT user_id=%s forwarded_to_group group_message_id=%s", user_chat_id, group_message_id)
    except Exception as e:
        log.exception("Failed to send message to group: %s", e)
        try:
            await query.edit_message_text("Couldn't reach the admins right now. Please try again in a moment.")
            await _delete_message_later(context, user_chat_id, query.message.message_id, delay_seconds=10)
        except Exception:
            pass
        return


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Keep chat clean: short welcome, auto-delete.
    await _send_ephemeral(context, update.message.chat_id, WELCOME_MESSAGE, delay_seconds=10)


def main() -> None:
    import asyncio
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )
    app.add_handler(CommandHandler("start", on_start))
    app.add_handler(CallbackQueryHandler(on_callback_query))
    app.add_handler(MessageHandler(filters.UpdateType.EDITED_MESSAGE & filters.TEXT & ~filters.COMMAND, on_edited_private_message))
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
