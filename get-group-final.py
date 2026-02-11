#!/usr/bin/env python3
"""
Final group finder - proper async implementation
"""
import os
import asyncio
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is required")

async def find_groups():
    print("Group Finder")
    print("============")
    print("Checking for recent messages to find group IDs...")
    print()
    
    bot = Bot(token=BOT_TOKEN)
    
    try:
        # Get bot info
        print("Getting bot info...")
        bot_info = await bot.get_me()
        print(f"Bot: @{bot_info.username} (ID: {bot_info.id})")
        print()
        
        # Get recent updates
        print("Checking for recent updates...")
        updates = await bot.get_updates(limit=100, timeout=10)
        
        print(f"Found {len(updates)} recent updates")
        
        if not updates:
            print("\nNo recent updates found.")
            print("\nTry this:")
            print("1. Send a message in your test group RIGHT NOW")
            print("2. Run this script again immediately")
            return
        
        groups_found = {}
        
        for update in updates:
            if update.message and update.message.chat:
                chat = update.message.chat
                
                if chat.type in ['group', 'supergroup']:
                    if chat.id not in groups_found:
                        groups_found[chat.id] = {
                            'id': chat.id,
                            'title': chat.title or 'Untitled Group',
                            'type': chat.type,
                            'last_message': update.message.text or '[Media/Other]',
                            'from_user': update.message.from_user.first_name if update.message.from_user else 'Unknown'
                        }
        
        if not groups_found:
            print("\nNo groups found in recent updates.")
            print("\nPlease:")
            print("1. Go to your test group")
            print("2. Send a message like 'test'")
            print("3. Run this script again within 30 seconds")
        else:
            print(f"\n*** FOUND {len(groups_found)} GROUP(S) ***")
            print("=" * 50)
            
            for i, (group_id, info) in enumerate(groups_found.items(), 1):
                print(f"\n{i}. Group: {info['title']}")
                print(f"   ID: {group_id}")
                print(f"   Type: {info['type']}")
                print(f"   Last message: {info['last_message'][:40]}...")
                print(f"   From: {info['from_user']}")
                
            print("\n" + "=" * 50)
            print("\nTo switch to your test group:")
            print("1. Choose the correct group ID from above")
            print("2. Update your .env file:")
            print("   GROUP_ID=<your_chosen_group_id>")
            
            if len(groups_found) == 1:
                test_group_id = list(groups_found.keys())[0]
                print(f"\nSince there's only one group:")
                print(f"GROUP_ID={test_group_id}")
    
    except Exception as e:
        print(f"Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure BOT_TOKEN is correct in .env")
        print("2. Make sure bot is added to your groups as admin")
        print("3. Send a fresh message in your test group")

if __name__ == "__main__":
    asyncio.run(find_groups())