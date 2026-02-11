# Reply Bot – Step-by-step setup

This guide covers: **connecting the bot to a Telegram group**, **deploying on Render.com**, **using Supabase** (optional), and **webhooks**.

---

## 1. Connect the bot to a group

### 1.1 Create the bot and get the token

1. Open Telegram and search for **@BotFather**.
2. Send `/newbot`, choose a name and username (e.g. `Reply Bot`, `my_reply_bot`).
3. Copy the **API token** (e.g. `123456789:ABCdefGHI...`). This is your `BOT_TOKEN`.

### 1.2 Create the group and add the bot

1. Create a **new group** in Telegram (or use an existing one).
2. **Add your bot** to the group (via “Add members” → search for your bot).
3. (Optional) Make the bot an **admin** so it can read all messages and reply.

### 1.3 Get the group ID

1. Send **any message** in the group (e.g. “hello”).
2. In a browser, open (replace `YOUR_BOT_TOKEN` with your token):
   ```
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```
3. In the JSON, find the chat object for your group. Its **`id`** is the **group ID** (e.g. `-1001234567890`).  
   That number is your `GROUP_ID`.

---

## 2. Deploy on Render.com

### 2.1 Push the repo to GitHub

1. Create a **GitHub** repo and push this project:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/reply-bot.git
   git push -u origin main
   ```

### 2.2 Create a Web Service on Render

1. Go to [render.com](https://render.com) and sign in (e.g. with GitHub).
2. **Dashboard** → **New** → **Web Service**.
3. Connect the **reply-bot** repository.
4. Use:
   - **Name:** `reply-bot` (or any name).
   - **Region:** choose one (e.g. Oregon).
   - **Branch:** `main`.
   - **Runtime:** **Node**.
   - **Build command:** `npm install && npm run build`
   - **Start command:** `npm start`

### 2.3 Set environment variables on Render

In the Render service → **Environment** tab, add:

| Key | Value | Notes |
|-----|--------|--------|
| `BOT_TOKEN` | Your bot token from BotFather | Required |
| `GROUP_ID` | The group ID (e.g. `-1001234567890`) | Required |
| `WEBHOOK_BASE_URL` | Your Render URL, e.g. `https://reply-bot-xxxx.onrender.com` | Required for webhook; use the URL Render gives you **after** first deploy |
| `WEBHOOK_SECRET` | A random secret path (e.g. `my-secret-webhook-path`) | Optional; default is `reply-bot-webhook` |
| `NODE_ENV` | `production` | Optional; good for production |

Optional (customize messages):

- `WELCOME_MESSAGE` – message when user sends `/start`
- `MESSAGE_AFTER` – message sent to user after they send a message (e.g. “We’ll get back to you…”)

After the **first deploy**, copy your service URL (e.g. `https://reply-bot-xxxx.onrender.com`), set `WEBHOOK_BASE_URL` to that URL (no trailing slash), then **Redeploy** so the bot registers the webhook.

### 2.4 (Optional) Use Blueprint instead of manual setup

If you use the `render.yaml` in the repo:

1. **New** → **Blueprint**.
2. Connect the repo; Render will create the Web Service from the blueprint.
3. In the **Environment** tab, set `BOT_TOKEN`, `GROUP_ID`, and `WEBHOOK_BASE_URL` (and optionally `WEBHOOK_SECRET`, Supabase vars).  
   Set `WEBHOOK_BASE_URL` after the first deploy, then redeploy.

---

## 3. Webhook (how it works on Render)

- **Locally:** the app uses **polling** (no `PORT` / `WEBHOOK_BASE_URL`).
- **On Render:** when `PORT` and `WEBHOOK_BASE_URL` are set, the app:
  1. Starts an HTTP server on `PORT` (Render sets this).
  2. Registers with Telegram: `setWebhook(WEBHOOK_BASE_URL/WEBHOOK_SECRET)`.
  3. Telegram sends updates to that URL; the app handles them and replies.

So **webhook is automatically used on Render** once you set:

- `PORT` (Render sets this)
- `WEBHOOK_BASE_URL` = your Render service URL (e.g. `https://reply-bot-xxxx.onrender.com`)

No extra step besides setting env vars and redeploying after you have the URL.

---

## 4. Supabase (optional database)

Supabase is used to store **message threads** (which group message belongs to which user). That makes replies more reliable than parsing the message text.

### 4.1 Create a Supabase project

1. Go to [supabase.com](https://supabase.com) and create a project.
2. Wait for the DB to be ready.

### 4.2 Create the table

1. In the Supabase dashboard: **SQL Editor** → **New query**.
2. Paste and run the contents of **`supabase/schema.sql`** in this repo (creates `message_threads` and RLS).

### 4.3 Get API keys

1. **Project Settings** → **API**.
2. Copy:
   - **Project URL** → use as `SUPABASE_URL`
   - **service_role** key (secret) → use as `SUPABASE_SERVICE_KEY`  
   Do not use the anon key for this bot; use the service role so the app can read/write `message_threads`.

### 4.4 Add to Render

In the Render service **Environment** tab, add:

| Key | Value |
|-----|--------|
| `SUPABASE_URL` | Your project URL |
| `SUPABASE_SERVICE_KEY` | Your service_role key |

Redeploy. If both are set, the bot will use Supabase for reply routing; if either is missing, it falls back to parsing the message text.

---

## 5. Quick checklist

- [ ] Bot created with BotFather; `BOT_TOKEN` copied.
- [ ] Group created; bot added (and optionally admin).
- [ ] Group ID obtained from `getUpdates`; `GROUP_ID` set.
- [ ] Repo pushed to GitHub; Render Web Service created; build/start commands set.
- [ ] `BOT_TOKEN`, `GROUP_ID`, `WEBHOOK_BASE_URL` set on Render; first deploy done.
- [ ] After first deploy: `WEBHOOK_BASE_URL` set to exact Render URL; redeploy.
- [ ] (Optional) Supabase project created; `schema.sql` run; `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` set on Render.

---

## 6. Local development (no webhook)

```bash
cp .env.example .env
# Edit .env: BOT_TOKEN=... and GROUP_ID=...
npm install
npm run build
npm start
```

Do **not** set `WEBHOOK_BASE_URL` or `PORT` in `.env` for local run; the app will use polling. For production (e.g. Render), set `PORT` and `WEBHOOK_BASE_URL` so the webhook is used.

---

## 7. Troubleshooting

- **Bot doesn’t reply in group:** Ensure the bot is in the group and can see messages (e.g. admin, or “Privacy mode” disabled in BotFather).
- **Webhook not receiving updates:** Check `WEBHOOK_BASE_URL` is exactly the Render URL (https, no trailing slash). Redeploy after changing it.
- **Render free tier sleep:** After idle time Render sleeps; the first message after wake-up may be slow. Webhook still works once the service is awake.
- **Supabase errors:** Confirm the table was created from `supabase/schema.sql` and that you’re using the **service_role** key, not anon.
