# Edit Feature Documentation

## Overview

The edit feature allows admins to review and modify their replies before sending them to users. When an admin replies to a user message in the group, instead of immediately sending the message, the bot creates a draft with "Send" and "Edit" buttons.

## How It Works

### 1. Admin Replies to User Message
- Admin replies to a user message in the group
- Instead of sending immediately, bot creates a draft message
- Draft is shown to the admin with inline keyboard buttons

### 2. Draft Message Format
```
📝 **Draft Reply:**

[Your message content here]

👆 Choose an action:
[✅ Send] [✏️ Edit]
```

### 3. Send Button
- Clicking "Send" immediately sends the message to the user
- User is removed from pending state (can send new messages)
- Draft is deleted and admin sees confirmation

### 4. Edit Button
- Clicking "Edit" enters edit mode
- Admin sees: "✏️ **Edit Mode** - Send your edited message as a reply to this message"
- Admin replies with the new/edited message
- Draft is updated with new content and shows Send/Edit buttons again

### 5. Edit Process
1. Admin clicks "Edit"
2. Bot shows edit instructions
3. Admin replies with edited message
4. Bot updates the draft with new content
5. Bot shows updated draft with Send/Edit buttons
6. Process repeats until admin clicks "Send"

## Technical Implementation

### New Data Structures
- `draft_messages`: Dictionary storing draft data for each admin
- `DRAFTS_FILE`: JSON file for persistent storage of drafts

### New Functions
- `create_send_edit_keyboard()`: Creates inline keyboard with Send/Edit buttons
- `save_draft()`: Saves draft data to memory and file
- `load_drafts()`: Loads drafts from file on startup
- `remove_draft()`: Removes draft when sent or cancelled
- `on_callback_query()`: Handles Send/Edit button clicks
- `on_edit_message()`: Handles message editing in edit mode

### Modified Functions
- `on_message()`: Now creates drafts instead of sending directly
- `main()`: Added CallbackQueryHandler for button interactions

## File Structure

### Draft Data Format
```json
{
  "admin_user_id": {
    "message": "The message content",
    "target_user_id": 12345,
    "is_editing": false,
    "message_id": 67890
  }
}
```

### Storage Files
- `data/threads.json`: Existing message thread mapping
- `data/drafts.json`: New draft message storage

## Benefits

1. **Review Before Send**: Admins can review messages before sending
2. **Edit Capability**: Easy to fix typos or improve messages
3. **No Accidental Sends**: Prevents immediate sending of replies
4. **Clean Interface**: Simple two-button interface
5. **Persistent Storage**: Drafts survive bot restarts

## Usage Example

1. User sends: "I need help with my order"
2. Admin replies in group: "I'll check your order status and get back to you shortly"
3. Bot shows admin: Draft with Send/Edit buttons
4. Admin clicks "Edit"
5. Admin replies: "I'll check your order status right away and resolve this for you"
6. Bot updates draft with new message and shows Send/Edit buttons
7. Admin clicks "Send"
8. User receives: "I'll check your order status right away and resolve this for you"

## Notes

- Each admin can have only one active draft at a time
- Drafts are automatically cleaned up when sent
- Edit mode is indicated by `is_editing: true` in draft data
- Original user message context is preserved throughout editing
- Bot handles all error cases gracefully