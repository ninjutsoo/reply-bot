#!/usr/bin/env python3
"""
Live group finder - starts the bot temporarily to capture group messages
"""
import os
import asyncio
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is required")

print("Live Group Finder")
print("=================")
print("This will start the bot temporarily to detect group messages.")
print("Send a message in your test group now...")
print("Press Ctrl+C to stop when you see your group ID.\n")

found_groups = {}

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture all messages to find group IDs"""
    msg = update.message
    if not msg:
        return
    
    chat = msg.chat
    chat_id = chat.id
    
    if chat.type in ['group', 'supergroup']:
        if chat_id not in found_groups:
            found_groups[chat_id] = {
                'id': chat_id,
                'title': chat.title or 'Untitled Group',
                'type': chat.type
            }
            
            print(f"*** FOUND GROUP ***")
            print(f"   Name: {chat.title or 'Untitled Group'}")
            print(f"   ID: {chat_id}")
            print(f"   Type: {chat.type}")
            print(f"   Message from: {msg.from_user.first_name if msg.from_user else 'Unknown'}")
            print(f"   Message: {msg.text[:50] if msg.text else '[Media/Other]'}...")
            print()
            
            # Show how to update .env
            print(f"To use this group, update your .env file:")
            print(f"GROUP_ID={chat_id}")
            print("-" * 50)
    
    elif chat.type == 'private':
        print(f"Private message from {msg.from_user.first_name if msg.from_user else 'Unknown'}: {msg.text[:30] if msg.text else '[Media]'}...")

async def main():
    """Run the live group finder"""
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handler for all text messages
    app.add_handler(MessageHandler(filters.ALL, on_message))
    
    print("Bot started! Send messages in your groups now...")
    print("The bot will show group IDs as it receives messages.")
    print()
    
    try:
        # Start polling
        await app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        print("\n\nStopping bot...")
        if found_groups:
            print("\nSummary of found groups:")
            for group_id, info in found_groups.items():
                print(f"   {info['title']} -> ID: {group_id}")
        else:
            print("\nNo groups detected. Make sure:")
            print("   1. Bot is added to your groups as admin")
            print("   2. You sent messages in the groups while this was running")
        print("\nDone!")

if __name__ == "__main__":
    asyncio.run(main())