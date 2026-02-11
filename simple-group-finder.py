#!/usr/bin/env python3
"""
Simple group finder using synchronous approach
"""
import os
import time
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is required")

print("Simple Group Finder")
print("===================")
print("This will check for recent messages to find group IDs.")
print()

def find_groups():
    bot = Bot(token=BOT_TOKEN)
    
    try:
        print("Getting bot info...")
        bot_info = bot.get_me()
        print(f"Bot: @{bot_info.username} (ID: {bot_info.id})")
        print()
        
        print("Checking for recent updates...")
        updates = bot.get_updates(limit=100, timeout=10)
        
        print(f"Found {len(updates)} recent updates")
        
        if not updates:
            print("\nNo recent updates found.")
            print("\nTry this:")
            print("1. Send a message in your test group")
            print("2. Wait 10 seconds") 
            print("3. Run this script again")
            return
        
        groups_found = {}
        
        for i, update in enumerate(updates):
            if update.message and update.message.chat:
                chat = update.message.chat
                
                if chat.type in ['group', 'supergroup']:
                    if chat.id not in groups_found:
                        groups_found[chat.id] = {
                            'id': chat.id,
                            'title': chat.title or 'Untitled Group',
                            'type': chat.type
                        }
                        
                        print(f"\n*** GROUP FOUND ***")
                        print(f"Name: {chat.title or 'Untitled Group'}")
                        print(f"ID: {chat.id}")
                        print(f"Type: {chat.type}")
                        
                        if update.message.from_user:
                            print(f"Last message from: {update.message.from_user.first_name}")
                        
                        if update.message.text:
                            print(f"Message: {update.message.text[:50]}...")
                        
                        print(f"\nTo use this group, update .env:")
                        print(f"GROUP_ID={chat.id}")
                        print("-" * 40)
        
        if not groups_found:
            print("\nNo groups found in recent updates.")
            print("Make sure you sent a message in your test group recently.")
        else:
            print(f"\nSummary: Found {len(groups_found)} group(s)")
            for group_id, info in groups_found.items():
                print(f"  {info['title']} -> {group_id}")
    
    except Exception as e:
        print(f"Error: {e}")
        print("\nMake sure:")
        print("1. BOT_TOKEN is correct in .env")
        print("2. Bot has been added to your groups")
        print("3. You sent messages in the groups recently")

if __name__ == "__main__":
    find_groups()