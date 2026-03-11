import logging
import asyncio
import httpx
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ============================================================
# Ø§Ù„Ù…ÙØ§ØªÙŠØ­ ØªÙÙ‚Ø±Ø£ Ù…Ù† Environment Variables
# Ù„Ø§ Ø´ÙŠØ¡ Ø³Ø±ÙŠ ÙÙŠ Ø§Ù„ÙƒÙˆØ¯ â€” GitHub Ø¢Ù…Ù† 100%
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY")
ADSTERRA_LINK = os.environ.get("ADSTERRA_LINK")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing!")
if not OPENROUTER_KEY:
    raise ValueError("OPENROUTER_KEY missing!")
if not ADSTERRA_LINK:
    raise ValueError("ADSTERRA_LINK missing!")
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

waiting_users = []
active_chats = {}
ai_chats = {}
user_msg_count = {}

async def ask_ai(user_id: int, user_message: str) -> str:
    if user_id not in ai_chats:
        ai_chats[user_id] = [
            {
                "role": "system",
                "content": (
                    "You are a friendly anonymous stranger on a chat platform. "
                    "Act like a real human having a casual conversation. "
                    "Keep replies short (1-3 sentences). "
                    "Be curious, friendly, and natural. "
                    "Never reveal you are an AI. "
                    "If asked your name say something like 'I prefer to stay anonymous'. "
                    "Match the language the user writes in."
                )
            }
        ]

    ai_chats[user_id].append({"role": "user", "content": user_message})

    if len(ai_chats[user_id]) > 11:
        ai_chats[user_id] = [ai_chats[user_id][0]] + ai_chats[user_id][-10:]

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "meta-llama/llama-3.1-8b-instruct:free",
                    "messages": ai_chats[user_id],
                    "max_tokens": 100
                }
            )
            data = response.json()
            reply = data["choices"][0]["message"]["content"]
            ai_chats[user_id].append({"role": "assistant", "content": reply})
            return reply
    except Exception as e:
        logger.error(f"OpenRouter error: {e}")
        return "haha yeah what do you think?"

async def try_match(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    if user_id in waiting_users:
        waiting_users.remove(user_id)

    if waiting_users:
        partner_id = waiting_users.pop(0)
        active_chats[user_id] = partner_id
        active_chats[partner_id] = user_id
        ai_chats.pop(user_id, None)
        ai_chats.pop(partner_id, None)

        msg = (
            "Connected!\n\n"
            "You are now chatting with a stranger.\n"
            "They cannot see who you are.\n\n"
            "Say hi!"
        )
        await context.bot.send_message(chat_id=user_id, text=msg)
        await context.bot.send_message(chat_id=partner_id, text=msg)
    else:
        waiting_users.append(user_id)
        await context.bot.send_message(
            chat_id=user_id,
            text="Looking for a stranger..."
        )
        asyncio.create_task(start_ai_after_delay(user_id, context))

async def start_ai_after_delay(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    await asyncio.sleep(10)
    if user_id in waiting_users and user_id not in active_chats:
        waiting_users.remove(user_id)
        active_chats[user_id] = "AI"
        await context.bot.send_message(
            chat_id=user_id,
            text="A stranger just joined! Say hi!"
        )

async def end_chat(user_id: int, context: ContextTypes.DEFAULT_TYPE, silent=False):
    partner_id = active_chats.pop(user_id, None)
    if partner_id and partner_id != "AI":
        active_chats.pop(partner_id, None)
        if not silent:
            await context.bot.send_message(
                chat_id=partner_id,
                text="Stranger has left. Press /start to find someone new."
            )
    ai_chats.pop(user_id, None)
    user_msg_count.pop(user_id, None)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in active_chats:
        await end_chat(user_id, context, silent=True)
    if user_id in waiting_users:
        waiting_users.remove(user_id)

    keyboard = [[
        InlineKeyboardButton("One quick step then chat!", url=ADSTERRA_LINK)
    ], [
        InlineKeyboardButton("I am ready â€” Find me a stranger!", callback_data="find_stranger")
    ]]

    await update.message.reply_text(
        "Welcome to AnonStrangerChat!\n\n"
        "Talk to a random stranger.\n"
        "Completely anonymous. No name. No photo.\n\n"
        "Before we begin â€” one quick step below:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id in active_chats or user_id in waiting_users:
        await end_chat(user_id, context)
        if user_id in waiting_users:
            waiting_users.remove(user_id)

        keyboard = [[
            InlineKeyboardButton("Find new stranger", callback_data="find_stranger")
        ]]
        await update.message.reply_text(
            "Chat ended. Want to talk to someone new?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text("You are not in a chat. Press /start to begin!")

async def next_stranger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await end_chat(user_id, context)

    keyboard = [[
        InlineKeyboardButton("Quick step first!", url=ADSTERRA_LINK)
    ], [
        InlineKeyboardButton("Find next stranger!", callback_data="find_stranger")
    ]]
    await update.message.reply_text(
        "Finding next stranger... One quick step below:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await end_chat(user_id, context)
    await update.message.reply_text(
        "Reported. Thank you for keeping this community safe.\n"
        "Press /start to find someone new."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "AnonStrangerChat â€” How it works:\n\n"
        "/start â€” Find a stranger to chat with\n"
        "/stop â€” End current chat\n"
        "/next â€” Find a new stranger\n"
        "/report â€” Report inappropriate behavior\n\n"
        "Stay anonymous. Be respectful. Have fun!"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "find_stranger":
        await query.edit_message_reply_markup(reply_markup=None)
        await try_match(user_id, context)

async def send_pending_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id in active_chats and "pending_msg" in context.user_data:
        text = context.user_data.pop("pending_msg")
        partner_id = active_chats[user_id]
        await query.edit_message_reply_markup(reply_markup=None)
        await deliver_message(user_id, partner_id, text, context)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    bad_words = ["nude", "porn", "naked", "xxx"]
    if any(word in text.lower() for word in bad_words):
        await update.message.reply_text("Please keep the conversation respectful.")
        return

    if user_id not in active_chats:
        await update.message.reply_text("You are not in a chat. Press /start to begin!")
        return

    partner_id = active_chats[user_id]
    user_msg_count[user_id] = user_msg_count.get(user_id, 0) + 1

    if user_msg_count[user_id] % 5 == 0:
        keyboard = [[
            InlineKeyboardButton("Quick step then your message arrives!", url=ADSTERRA_LINK)
        ], [
            InlineKeyboardButton("Done! Send my message", callback_data=f"send_{user_id}")
        ]]
        await update.message.reply_text(
            "Delivering your message... One quick step below:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data["pending_msg"] = text
        return

    await deliver_message(user_id, partner_id, text, context)

async def deliver_message(user_id, partner_id, text, context):
    import random

    if partner_id == "AI":
        ai_reply = await ask_ai(user_id, text)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Stranger: {ai_reply}"
        )
        if random.random() < 0.3 and waiting_users:
            real_partner = waiting_users.pop(0)
            active_chats[user_id] = real_partner
            active_chats[real_partner] = user_id
            ai_chats.pop(user_id, None)
            await context.bot.send_message(
                chat_id=user_id,
                text="Connected to a real stranger now!"
            )
            await context.bot.send_message(
                chat_id=real_partner,
                text="Connected! Say hi!"
            )
    else:
        try:
            await context.bot.send_message(
                chat_id=partner_id,
                text=f"Stranger: {text}"
            )
        except Exception:
            await context.bot.send_message(
                chat_id=user_id,
                text="Stranger disconnected. Press /start to find someone new."
            )
            active_chats.pop(user_id, None)
            active_chats.pop(partner_id, None)

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("next", next_stranger))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^find_stranger$"))
    app.add_handler(CallbackQueryHandler(send_pending_message, pattern="^send_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Bot started successfully!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
