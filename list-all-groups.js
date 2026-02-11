#!/usr/bin/env node
require('dotenv').config()
const https = require('https')

const token = process.env.BOT_TOKEN

if (!token) {
  console.error('Missing BOT_TOKEN in .env')
  process.exit(1)
}

console.log('🔍 Finding all groups your bot is in...')

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

async function findAllGroups() {
  try {
    // First, delete webhook to enable getUpdates
    console.log('🔧 Preparing to scan messages...')
    const deleteWebhookUrl = `https://api.telegram.org/bot${token}/deleteWebhook`
    await makeRequest(deleteWebhookUrl)
    console.log('✓ Webhook deleted (if it was active)')

    // Get bot info
    const getBotUrl = `https://api.telegram.org/bot${token}/getMe`
    const botResult = await makeRequest(getBotUrl)
    
    if (!botResult.ok) {
      throw new Error(`Failed to get bot info: ${botResult.description}`)
    }
    
    const botInfo = botResult.result
    console.log(`🤖 Bot: @${botInfo.username} (ID: ${botInfo.id})`)

    // Wait a moment after deleting webhook
    await new Promise(resolve => setTimeout(resolve, 1000))

    // Get recent updates
    console.log('📡 Scanning recent messages...')
    const getUpdatesUrl = `https://api.telegram.org/bot${token}/getUpdates?limit=100`
    const updatesResult = await makeRequest(getUpdatesUrl)

    if (!updatesResult.ok) {
      throw new Error(`Failed to get updates: ${updatesResult.description}`)
    }

    const updates = updatesResult.result || []
    console.log(`📋 Found ${updates.length} recent updates`)

    // Find all unique groups
    const groups = new Map()
    
    updates.forEach(update => {
      if (update.message) {
        const chat = update.message.chat
        if (chat.type === 'group' || chat.type === 'supergroup') {
          groups.set(chat.id, {
            id: chat.id,
            title: chat.title || 'Untitled Group',
            type: chat.type,
            lastMessage: update.message.text || '[Media/Other]',
            lastMessageDate: new Date(update.message.date * 1000).toLocaleString(),
            fromUser: update.message.from ? 
              (update.message.from.first_name + (update.message.from.last_name ? ' ' + update.message.from.last_name : '')) : 
              'Unknown'
          })
        }
      }
    })

    if (groups.size === 0) {
      console.log('\n❌ No groups found in recent updates')
      console.log('\n💡 To find your groups:')
      console.log('1. Send a message in each group where your bot is added')
      console.log('2. Run this script again')
      console.log('3. The groups will appear in the list below')
    } else {
      console.log(`\n🎯 Found ${groups.size} group(s):`)
      console.log('=' .repeat(80))
      
      Array.from(groups.values()).forEach((group, index) => {
        console.log(`\n${index + 1}. Group: "${group.title}"`)
        console.log(`   📍 ID: ${group.id}`)
        console.log(`   📝 Type: ${group.type}`)
        console.log(`   💬 Last message: "${group.lastMessage.substring(0, 50)}${group.lastMessage.length > 50 ? '...' : ''}"`)
        console.log(`   👤 From: ${group.fromUser}`)
        console.log(`   🕒 Date: ${group.lastMessageDate}`)
      })
      
      console.log('\n' + '=' .repeat(80))
      console.log('\n✅ To use one of these groups, update your .env file:')
      console.log('GROUP_ID=<choose_the_correct_id_from_above>')
      
      if (groups.size === 1) {
        const groupId = Array.from(groups.values())[0].id
        console.log(`\n💡 Since there's only one group, you probably want:`)
        console.log(`GROUP_ID=${groupId}`)
      }
    }

  } catch (error) {
    console.error('❌ Error:', error.message)
    process.exit(1)
  }
}

// Run the script
findAllGroups()