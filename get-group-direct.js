#!/usr/bin/env node
require('dotenv').config()
const https = require('https')

const token = process.env.BOT_TOKEN

if (!token) {
  console.error('Missing BOT_TOKEN in .env')
  process.exit(1)
}

console.log('🔍 Getting group ID directly from recent activity...')

// Function to make API requests
function makeRequest(url, method = 'GET', postData = null) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url)
    const options = {
      hostname: urlObj.hostname,
      path: urlObj.pathname + urlObj.search,
      method: method,
      headers: {
        'Content-Type': 'application/json'
      }
    }

    const req = https.request(options, (res) => {
      let data = ''
      res.on('data', (chunk) => { data += chunk })
      res.on('end', () => {
        try {
          const result = JSON.parse(data)
          resolve(result)
        } catch (e) {
          reject(new Error(`Failed to parse response: ${data}`))
        }
      })
    })

    req.on('error', reject)
    
    if (postData) {
      req.write(JSON.stringify(postData))
    }
    
    req.end()
  })
}

async function getGroupId() {
  try {
    console.log('🤖 Bot: @reply_ffi_bot')
    console.log('📡 Getting recent updates with higher limit...')
    
    // Try with higher limit and offset
    const getUpdatesUrl = `https://api.telegram.org/bot${token}/getUpdates?limit=100&offset=-100`
    const updatesResult = await makeRequest(getUpdatesUrl)

    if (!updatesResult.ok) {
      throw new Error(`Failed to get updates: ${updatesResult.description}`)
    }

    const updates = updatesResult.result || []
    console.log(`📋 Found ${updates.length} updates`)

    if (updates.length === 0) {
      console.log('\n❌ No updates found')
      console.log('\n🔧 Troubleshooting steps:')
      console.log('1. Make sure your bot is ADMIN in the test group')
      console.log('2. Send a message that @mentions the bot: "@reply_ffi_bot test"')
      console.log('3. Try sending "/start" to the bot in the group')
      console.log('4. Wait 30 seconds and run this script again')
      return
    }

    // Find all chats (groups and private)
    const chats = new Map()
    
    updates.forEach((update, index) => {
      console.log(`\nUpdate ${index + 1}:`)
      
      if (update.message) {
        const chat = update.message.chat
        const from = update.message.from
        const text = update.message.text || '[Media/Other]'
        
        console.log(`  Type: ${chat.type}`)
        console.log(`  Chat ID: ${chat.id}`)
        console.log(`  Title: ${chat.title || chat.first_name || 'No title'}`)
        console.log(`  From: ${from ? (from.first_name + (from.last_name ? ' ' + from.last_name : '')) : 'Unknown'}`)
        console.log(`  Text: "${text.substring(0, 50)}${text.length > 50 ? '...' : ''}"`)
        
        if (chat.type === 'group' || chat.type === 'supergroup') {
          chats.set(chat.id, {
            id: chat.id,
            title: chat.title || 'Untitled Group',
            type: chat.type,
            lastMessage: text,
            fromUser: from ? (from.first_name + (from.last_name ? ' ' + from.last_name : '')) : 'Unknown'
          })
        }
      }
    })

    if (chats.size > 0) {
      console.log('\n🎯 GROUPS FOUND:')
      console.log('=' .repeat(50))
      
      Array.from(chats.values()).forEach((group, index) => {
        console.log(`\n${index + 1}. "${group.title}"`)
        console.log(`   ID: ${group.id}`)
        console.log(`   Type: ${group.type}`)
        console.log(`   Last message: "${group.lastMessage.substring(0, 30)}..."`)
        console.log(`   From: ${group.fromUser}`)
      })
      
      console.log('\n' + '=' .repeat(50))
      console.log('\n✅ To switch to your test group, update .env:')
      
      if (chats.size === 1) {
        const testGroupId = Array.from(chats.values())[0].id
        console.log(`GROUP_ID=${testGroupId}`)
        console.log(`\n💡 This is likely your test group ID: ${testGroupId}`)
      } else {
        console.log('GROUP_ID=<choose_the_test_group_id_from_above>')
        console.log('\n💡 Choose the ID of your test group from the list above')
      }
    } else {
      console.log('\n❌ No groups found in updates')
      console.log('All updates were from private chats or other sources')
    }

  } catch (error) {
    console.error('❌ Error:', error.message)
    process.exit(1)
  }
}

// Run the script
getGroupId()