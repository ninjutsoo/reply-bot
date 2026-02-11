import * as dotenv from 'dotenv'
import express from 'express'
import * as fs from 'fs'
import * as path from 'path'
import { Telegraf } from 'telegraf'
import type { Context } from 'telegraf'
import { createClient, SupabaseClient } from '@supabase/supabase-js'

dotenv.config()

// Local file store for message threads (reply resolution when Supabase not used)
const THREADS_FILE = path.join(process.cwd(), 'data', 'threads.json')
type ThreadRow = { group_chat_id: string; group_message_id: number; user_chat_id: number }
let threads: ThreadRow[] = []

function loadThreads(): void {
  try {
    const raw = fs.readFileSync(THREADS_FILE, 'utf-8')
    threads = JSON.parse(raw)
    if (!Array.isArray(threads)) threads = []
  } catch {
    threads = []
  }
}
function saveThread(row: ThreadRow): void {
  threads.push(row)
  try {
    fs.mkdirSync(path.dirname(THREADS_FILE), { recursive: true })
    fs.writeFileSync(THREADS_FILE, JSON.stringify(threads, null, 0), 'utf-8')
  } catch (e) {
    console.error('Failed to save thread:', e)
  }
}
function findUserByGroupMessage(groupChatId: string, groupMessageId: number): number | null {
  const row = threads.find(t => t.group_chat_id === groupChatId && t.group_message_id === groupMessageId)
  return row ? row.user_chat_id : null
}
loadThreads()

const BOT_TOKEN = process.env.BOT_TOKEN
const GROUP_ID = process.env.GROUP_ID
const PORT = process.env.PORT
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET || 'reply-bot-webhook'
const SUPABASE_URL = process.env.SUPABASE_URL
const SUPABASE_SERVICE_KEY = process.env.SUPABASE_SERVICE_KEY

if (typeof BOT_TOKEN !== 'string') throw new Error('BOT_TOKEN is required')
if (typeof GROUP_ID !== 'string' || !GROUP_ID.trim()) throw new Error('GROUP_ID is required (add bot to group, then get id from getUpdates)')
const token = BOT_TOKEN as string
const groupId = GROUP_ID.trim()

const useWebhook = Boolean(PORT && process.env.WEBHOOK_BASE_URL)
const useSupabase = Boolean(SUPABASE_URL && SUPABASE_SERVICE_KEY)

const welcomeMessage = process.env.WELCOME_MESSAGE || 'Send your message in one message. Our admins will receive it and reply to you here.'
const messageAfter = process.env.MESSAGE_AFTER || "We'll get back to you as soon as we can"
const waitingMessage = process.env.WAITING_MESSAGE || "Waiting for admins to reply. You can only send another message after they've replied to your previous message."

// Users who sent a message and are waiting for an admin reply (can't send again until replied)
const pendingUsers = new Set<number>()

let supabase: SupabaseClient | null = null
if (useSupabase) {
  supabase = createClient(SUPABASE_URL!, SUPABASE_SERVICE_KEY!)
}

const bot = new Telegraf(token)

async function sendMessageInGroup(text: string): Promise<number | null> {
  const result = await bot.telegram.sendMessage(groupId, text)
  return result?.message_id ?? null
}

async function resolveUserChatId(ctx: Context, replyToMessage: { text?: string; message_id: number }): Promise<number | null> {
  if (!replyToMessage?.message_id) return null
  const gid = groupId
  const mid = replyToMessage.message_id
  if (useSupabase) {
    const { data } = await supabase!
      .from('message_threads')
      .select('user_chat_id')
      .eq('group_chat_id', gid)
      .eq('group_message_id', mid)
      .single()
    if (data?.user_chat_id) return data.user_chat_id as number
  }
  const fromFile = findUserByGroupMessage(gid, mid)
  if (fromFile != null) return fromFile
  const text = replyToMessage?.text
  if (!text || !text.includes('<') || !text.includes('>')) return null
  const match = text.match(/User\s*<(-?\d+)>/)
  return match ? parseInt(match[1], 10) : null
}

const onMessage = async (ctx: Context) => {
  const msg = ctx.message
  if (!msg || !('text' in msg)) return

  // In the group: only treat replies to the BOT's messages as "reply to user"
  // Only respond in the configured group (GROUP_ID) — ignore if bot was added to other groups
  if (msg.reply_to_message) {
    if (String(ctx.chat?.id) !== groupId) return // not our group, ignore
    const fromBot = msg.reply_to_message.from?.is_bot === true
    if (!fromBot) return // ignore replies to other people's messages
    const userChatId = await resolveUserChatId(ctx, msg.reply_to_message)
    if (userChatId != null) {
      // Send reply to user as anonymous (no username/name of who replied)
      await ctx.telegram.sendMessage(userChatId, msg.text)
      pendingUsers.delete(userChatId) // they got a reply, can send again
    }
    return
  }

  // Only forward to group when user messages in private (DM)
  if (ctx.chat?.type !== 'private') return

  // In DM: block if user is already waiting for a reply
  if (pendingUsers.has(ctx.chat!.id)) {
    await ctx.reply(waitingMessage)
    return
  }

  // Show name and username in group (reply resolution via Supabase only)
  const from = ctx.from
  const fullName = [from?.first_name, from?.last_name].filter(Boolean).join(' ') || 'Unknown'
  const handle = from?.username ? ` (@${from.username})` : ''
  const userLine = `User: ${fullName}${handle}\n\n${msg.text}`
  await ctx.telegram.sendMessage(ctx.chat!.id, messageAfter)

  let groupMessageId: number | null = null
  try {
    groupMessageId = await sendMessageInGroup(userLine)
  } catch (e) {
    console.error('Failed to send message to group:', e)
    await ctx.telegram.sendMessage(ctx.chat!.id, "Couldn't reach the admins right now. Please try again in a moment.")
    return
  }

  if (groupMessageId == null) {
    console.error('Send to group returned no message id')
    await ctx.telegram.sendMessage(ctx.chat!.id, "Couldn't reach the admins right now. Please try again in a moment.")
    return
  }

  {
    const row: ThreadRow = { group_chat_id: groupId, group_message_id: groupMessageId, user_chat_id: ctx.chat!.id }
    saveThread(row)
    if (useSupabase) {
      await supabase!.from('message_threads').insert(row)
    }
    pendingUsers.add(ctx.chat!.id) // only block repeat after we know it reached the group
  }
}

bot.start((ctx) => ctx.reply(welcomeMessage))
bot.on('text', onMessage)

if (useWebhook) {
  const app = express()
  app.use(express.json())

  app.get('/health', (_req, res) => {
    res.status(200).json({ ok: true, bot: 'reply-bot' })
  })

  app.post(`/${WEBHOOK_SECRET}`, async (req, res) => {
    try {
      await bot.handleUpdate(req.body, res)
    } catch (err) {
      console.error('Webhook error:', err)
      res.status(200).end()
    }
  })

  const server = app.listen(Number(PORT), async () => {
    const baseUrl = process.env.WEBHOOK_BASE_URL!.replace(/\/$/, '')
    const webhookUrl = `${baseUrl}/${WEBHOOK_SECRET}`
    await bot.telegram.setWebhook(webhookUrl)
    console.log('Webhook set:', webhookUrl)
    console.log('Server listening on port', PORT)
  })

  process.once('SIGINT', () => {
    bot.stop('SIGINT')
    server.close()
  })
  process.once('SIGTERM', () => {
    bot.stop('SIGTERM')
    server.close()
  })
} else {
  bot.launch()
  process.once('SIGINT', () => bot.stop('SIGINT'))
  process.once('SIGTERM', () => bot.stop('SIGTERM'))
}
