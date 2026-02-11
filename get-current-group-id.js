#!/usr/bin/env node
// This script helps you get the group ID when you have the bot token
const readline = require('readline')
const https = require('https')

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
})

console.log('🤖 Bot Token and Group ID Recovery Tool')
console.log('=====================================\n')

rl.question('Enter your bot token: ', (token) => {
  if (!token || !token.includes(':')) {
    console.log('❌ Invalid bot token format')
    rl.close()
    return
  }

  console.log('\n🔧 Deleting webhook and getting updates...')
  
  // Delete webhook first
  const deleteWebhookUrl = `https://api.telegram.org/bot${token}/deleteWebhook`
  
  https.get(deleteWebhookUrl, (res) => {
    let data = ''
    res.on('data', (c) => { data += c })
    res.on('end', () => {
      const result = JSON.parse(data)
      if (!result.ok) {
        console.log('❌ Invalid bot token or API error:', result.description)
        rl.close()
        return
      }
      
      console.log('✓ Webhook deleted')
      
      // Get updates after a short delay
      setTimeout(() => {
        const getUpdatesUrl = `https://api.telegram.org/bot${token}/getUpdates`
        
        https.get(getUpdatesUrl, (res2) => {
          let data2 = ''
          res2.on('data', (c) => { data2 += c })
          res2.on('end', () => {
            const updates = JSON.parse(data2)
            if (!updates.ok) {
              console.log('❌ Error getting updates:', updates.description)
              rl.close()
              return
            }
            
            const messages = updates.result || []
            console.log(`📋 Found ${messages.length} recent updates`)
            
            // Find all groups
            const groups = new Map()
            
            messages.forEach(update => {
              if (update.message && (update.message.chat.type === 'group' || update.message.chat.type === 'supergroup')) {
                const chat = update.message.chat
                groups.set(chat.id, {
                  id: chat.id,
                  title: chat.title || 'Untitled Group',
                  type: chat.type
                })
              }
            })
            
            if (groups.size === 0) {
              console.log('\n❌ No groups found in recent updates')
              console.log('💡 Make sure:')
              console.log('   1. Your bot is added to the group')
              console.log('   2. Someone sent a message in the group recently')
              console.log('   3. Run this script again after sending a message')
            } else {
              console.log('\n📋 Found these groups:')
              Array.from(groups.values()).forEach((group, index) => {
                console.log(`${index + 1}. "${group.title}" - ID: ${group.id}`)
              })
              
              console.log('\n✅ Your .env file should contain:')
              console.log(`BOT_TOKEN=${token}`)
              
              if (groups.size === 1) {
                const groupId = Array.from(groups.values())[0].id
                console.log(`GROUP_ID=${groupId}`)
              } else {
                console.log('GROUP_ID=<choose_the_correct_id_from_above>')
              }
            }
            
            rl.close()
          })
        }).on('error', (e) => {
          console.log('❌ Error:', e.message)
          rl.close()
        })
      }, 1000)
    })
  }).on('error', (e) => {
    console.log('❌ Error:', e.message)
    rl.close()
  })
})