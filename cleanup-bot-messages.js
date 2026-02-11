#!/usr/bin/env node
require('dotenv').config()
const https = require('https')

const token = process.env.BOT_TOKEN
const groupId = process.env.GROUP_ID

if (!token) {
  console.error('Missing BOT_TOKEN in .env')
  process.exit(1)
}

if (!groupId) {
  console.error('Missing GROUP_ID in .env')
  process.exit(1)
}

console.log(`🧹 Cleaning up bot messages in group ${groupId}...`)

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

// Function to delete a message
async function deleteMessage(messageId) {
  try {
    const url = `https://api.telegram.org/bot${token}/deleteMessage`
    const result = await makeRequest(url, 'POST', {
      chat_id: groupId,
      message_id: messageId
    })
    
    if (result.ok) {
      console.log(`✓ Deleted message ${messageId}`)
      return true
    } else {
      console.log(`✗ Failed to delete message ${messageId}: ${result.description}`)
      return false
    }
  } catch (error) {
    console.log(`✗ Error deleting message ${messageId}: ${error.message}`)
    return false
  }
}

// Function to get bot info
async function getBotInfo() {
  try {
    const url = `https://api.telegram.org/bot${token}/getMe`
    const result = await makeRequest(url)
    
    if (result.ok) {
      return result.result
    } else {
      throw new Error(`Failed to get bot info: ${result.description}`)
    }
  } catch (error) {
    throw new Error(`Error getting bot info: ${error.message}`)
  }
}

// Main cleanup function
async function cleanupBotMessages() {
  try {
    // First, delete webhook to enable getUpdates
    console.log('🔧 Preparing to scan messages...')
    const deleteWebhookUrl = `https://api.telegram.org/bot${token}/deleteWebhook`
    await makeRequest(deleteWebhookUrl)
    console.log('✓ Webhook deleted (if it was active)')

    // Get bot info
    const botInfo = await getBotInfo()
    const botId = botInfo.id
    console.log(`🤖 Bot: @${botInfo.username} (ID: ${botId})`)

    // Wait a moment after deleting webhook
    await new Promise(resolve => setTimeout(resolve, 1000))

    // Get recent updates to find bot messages
    console.log('📡 Scanning recent messages...')
    const getUpdatesUrl = `https://api.telegram.org/bot${token}/getUpdates?limit=100`
    const updatesResult = await makeRequest(getUpdatesUrl)

    if (!updatesResult.ok) {
      throw new Error(`Failed to get updates: ${updatesResult.description}`)
    }

    const updates = updatesResult.result || []
    console.log(`📋 Found ${updates.length} recent updates`)

    // Find messages sent by the bot in the target group
    const botMessages = []
    
    for (const update of updates) {
      if (update.message && 
          String(update.message.chat.id) === String(groupId) && 
          update.message.from && 
          update.message.from.id === botId) {
        botMessages.push(update.message.message_id)
      }
    }

    if (botMessages.length === 0) {
      console.log('✅ No bot messages found in recent updates')
      console.log('💡 Note: This only scans recent messages (last ~100 updates)')
      console.log('💡 Older bot messages may still exist but are not accessible via API')
      return
    }

    console.log(`🎯 Found ${botMessages.length} bot messages to delete`)
    
    // Delete messages with delay to avoid rate limiting
    let deleted = 0
    let failed = 0
    
    for (const messageId of botMessages) {
      const success = await deleteMessage(messageId)
      if (success) {
        deleted++
      } else {
        failed++
      }
      
      // Small delay to avoid rate limiting
      await new Promise(resolve => setTimeout(resolve, 100))
    }

    console.log(`\n📊 Cleanup Summary:`)
    console.log(`✅ Successfully deleted: ${deleted} messages`)
    console.log(`❌ Failed to delete: ${failed} messages`)
    
    if (failed > 0) {
      console.log(`\n💡 Some messages couldn't be deleted (they might be too old or already deleted)`)
    }

    console.log(`\n🎉 Cleanup completed!`)

  } catch (error) {
    console.error('❌ Cleanup failed:', error.message)
    process.exit(1)
  }
}

// Run the cleanup
cleanupBotMessages()