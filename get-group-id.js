#!/usr/bin/env node
require('dotenv').config()
const token = process.env.BOT_TOKEN
if (!token) {
  console.error('Missing BOT_TOKEN in .env')
  process.exit(1)
}
const url = `https://api.telegram.org/bot${token}/getUpdates`
require('https').get(url, (res) => {
  let data = ''
  res.on('data', (c) => { data += c })
  res.on('end', () => {
    const j = JSON.parse(data)
    if (!j.ok) {
      console.error('API error:', j)
      process.exit(1)
    }
    const updates = j.result || []
    const group = updates.find(u => u.message?.chat?.type === 'group' || u.message?.chat?.type === 'supergroup')
    if (group) {
      const id = group.message.chat.id
      console.log('Group ID:', id)
      console.log('Add to .env:  GROUP_ID=' + id)
    } else {
      console.log('No group chat found in getUpdates.')
      console.log('1. Add your bot to the group')
      console.log('2. Send any message in the group')
      console.log('3. Run this script again:  node get-group-id.js')
    }
  })
}).on('error', (e) => {
  console.error(e)
  process.exit(1)
})
