#!/usr/bin/env node
require('dotenv').config()
const https = require('https')

const token = process.env.BOT_TOKEN
if (!token) {
  console.error('Missing BOT_TOKEN in .env')
  process.exit(1)
}

console.log('Getting test group ID...')

// First, delete webhook to enable getUpdates
const deleteWebhookUrl = `https://api.telegram.org/bot${token}/deleteWebhook`

https.get(deleteWebhookUrl, (res) => {
  let data = ''
  res.on('data', (c) => { data += c })
  res.on('end', () => {
    const result = JSON.parse(data)
    if (result.ok) {
      console.log('✓ Webhook deleted successfully')
      
      // Now get updates
      setTimeout(() => {
        const getUpdatesUrl = `https://api.telegram.org/bot${token}/getUpdates`
        https.get(getUpdatesUrl, (res2) => {
          let data2 = ''
          res2.on('data', (c) => { data2 += c })
          res2.on('end', () => {
            const j = JSON.parse(data2)
            if (!j.ok) {
              console.error('API error:', j)
              process.exit(1)
            }
            const updates = j.result || []
            console.log(`Found ${updates.length} recent updates`)
            
            // Find all groups
            const groups = updates.filter(u => 
              u.message?.chat?.type === 'group' || 
              u.message?.chat?.type === 'supergroup'
            )
            
            if (groups.length === 0) {
              console.log('\n❌ No group chats found in recent updates.')
              console.log('\nTo get your test group ID:')
              console.log('1. Add your bot to the test group')
              console.log('2. Send any message in the test group')
              console.log('3. Run this script again: node get-test-group-id.js')
            } else {
              console.log('\n📋 Found these groups:')
              groups.forEach((group, index) => {
                const chat = group.message.chat
                console.log(`${index + 1}. "${chat.title}" - ID: ${chat.id}`)
              })
              
              if (groups.length === 1) {
                const groupId = groups[0].message.chat.id
                console.log(`\n✅ Use this GROUP_ID for testing: ${groupId}`)
                console.log(`\nAdd to your .env file:`)
                console.log(`GROUP_ID=${groupId}`)
              } else {
                console.log(`\n📝 Choose the correct group ID from the list above`)
                console.log(`Add the chosen ID to your .env file as: GROUP_ID=your_chosen_id`)
              }
            }
          })
        }).on('error', (e) => {
          console.error('Error getting updates:', e)
          process.exit(1)
        })
      }, 1000) // Wait 1 second after deleting webhook
      
    } else {
      console.error('Failed to delete webhook:', result)
      process.exit(1)
    }
  })
}).on('error', (e) => {
  console.error('Error deleting webhook:', e)
  process.exit(1)
})