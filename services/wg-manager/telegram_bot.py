#!/usr/bin/env python3
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import settings
import wg_manager

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


application: Application = None

AUTO_DELETE_TIMEOUT = 3600


async def auto_delete_message(message, delay: int = AUTO_DELETE_TIMEOUT):
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception as e:
        logger.debug(f"Could not delete message: {e}")


def is_authorized(chat_id: int) -> bool:
    """Check if chat is authorized to use the bot."""
    if not settings.telegram_chat_id:
        return True  # No restrictions if not configured
    return chat_id == settings.telegram_chat_id


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        msg = await update.message.reply_text(f"⛔ Access denied. Chat ID: `{update.effective_chat.id}`", parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg, 60))
        return
    
    keyboard = [
        [
            InlineKeyboardButton("🔄 Restart All", callback_data="restart_all"),
        ],
        [
            InlineKeyboardButton("🏠 Restart Internal", callback_data="restart_internal"),
            InlineKeyboardButton("🌍 Restart External", callback_data="restart_external"),
        ],
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
        ],
        [
            InlineKeyboardButton("👤 Create User", callback_data="create_user_prompt"),
            InlineKeyboardButton("🗑 Delete User", callback_data="delete_user_prompt"),
        ],
        [
            InlineKeyboardButton("📋 List Users", callback_data="list_users"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await update.message.reply_text(
        "🔐 *WireGuard Manager*\n\nSelect an action:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    # Auto-delete menu after 1 hour
    asyncio.create_task(auto_delete_message(msg))
    # Delete user's command message
    asyncio.create_task(auto_delete_message(update.message, 5))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        msg = await update.message.reply_text(f"⛔ Access denied. Chat ID: `{update.effective_chat.id}`", parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg, 60))
        return
    
    help_text = """
🔐 *WireGuard Manager Commands*

/start - Show main menu
/restart - Restart all tunnels
/restart\\_internal - Restart internal node
/restart\\_external - Restart external node
/status - Show tunnel status
/create\\_user <name> - Create new user
/delete\\_user <name> - Delete user
/list\\_users - List all users
/help - Show this help

You can also use the inline buttons from /start
"""
    msg = await update.message.reply_text(help_text, parse_mode="Markdown")
    asyncio.create_task(auto_delete_message(msg))
    asyncio.create_task(auto_delete_message(update.message, 5))


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        msg = await update.message.reply_text(f"⛔ Access denied. Chat ID: `{update.effective_chat.id}`", parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg, 60))
        return
    
    msg = await update.message.reply_text("🔄 Restarting all tunnels...")
    
    internal_result, external_result = wg_manager.restart_all()
    
    response = "🔄 *Restart Results*\n\n"
    response += f"🏠 *Internal:* {'✅' if internal_result.success else '❌'}\n"
    if internal_result.error:
        response += f"```\n{internal_result.error[:200]}\n```\n"
    
    response += f"\n🌍 *External:* {'✅' if external_result.success else '❌'}\n"
    if external_result.error:
        response += f"```\n{external_result.error[:200]}\n```\n"
    
    await msg.edit_text(response, parse_mode="Markdown")
    asyncio.create_task(auto_delete_message(msg))
    asyncio.create_task(auto_delete_message(update.message, 5))


async def restart_internal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        msg = await update.message.reply_text(f"⛔ Access denied. Chat ID: `{update.effective_chat.id}`", parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg, 60))
        return
    
    msg = await update.message.reply_text("🔄 Restarting internal tunnel...")
    result = wg_manager.restart_internal()
    
    response = f"🏠 *Internal Restart:* {'✅ Success' if result.success else '❌ Failed'}\n"
    if result.error:
        response += f"```\n{result.error[:300]}\n```"
    
    await msg.edit_text(response, parse_mode="Markdown")
    asyncio.create_task(auto_delete_message(msg))
    asyncio.create_task(auto_delete_message(update.message, 5))


async def restart_external_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        msg = await update.message.reply_text(f"⛔ Access denied. Chat ID: `{update.effective_chat.id}`", parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg, 60))
        return
    
    msg = await update.message.reply_text("🔄 Restarting external tunnel...")
    result = wg_manager.restart_external()
    
    response = f"🌍 *External Restart:* {'✅ Success' if result.success else '❌ Failed'}\n"
    if result.error:
        response += f"```\n{result.error[:300]}\n```"
    
    await msg.edit_text(response, parse_mode="Markdown")
    asyncio.create_task(auto_delete_message(msg))
    asyncio.create_task(auto_delete_message(update.message, 5))


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        msg = await update.message.reply_text(f"⛔ Access denied. Chat ID: `{update.effective_chat.id}`", parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg, 60))
        return
    
    msg = await update.message.reply_text("📊 Getting status...")
    
    internal = wg_manager.get_status_internal()
    external = wg_manager.get_status_external()
    
    response = "📊 *WireGuard Status*\n\n"
    response += f"🏠 *Internal:* {'✅' if internal.success else '❌'}\n"
    if internal.output:
        output = internal.output[:500] + "..." if len(internal.output) > 500 else internal.output
        response += f"```\n{output}\n```\n"
    
    response += f"\n🌍 *External:* {'✅' if external.success else '❌'}\n"
    if external.output:
        output = external.output[:500] + "..." if len(external.output) > 500 else external.output
        response += f"```\n{output}\n```"
    
    await msg.edit_text(response, parse_mode="Markdown")
    asyncio.create_task(auto_delete_message(msg))
    asyncio.create_task(auto_delete_message(update.message, 5))


async def create_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        msg = await update.message.reply_text(f"⛔ Access denied. Chat ID: `{update.effective_chat.id}`", parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg, 60))
        return
    
    if not context.args:
        msg = await update.message.reply_text("Usage: /create\\_user <username>", parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg))
        asyncio.create_task(auto_delete_message(update.message, 5))
        return
    
    username = context.args[0]
    msg = await update.message.reply_text(f"👤 Creating user `{username}`...", parse_mode="Markdown")
    
    try:
        result = wg_manager.create_user(username)
        
        response = f"✅ *User Created*\n\n"
        response += f"👤 *Username:* `{result['username']}`\n"
        response += f"🌐 *IP:* `{result['ip']}`\n"
        response += f"📄 *Config:* `{result['config_path']}`\n"
        
        await msg.edit_text(response, parse_mode="Markdown")
        # Delete status message, but keep user configs
        asyncio.create_task(auto_delete_message(msg))
        
        # Send QR code (keep forever)
        from pathlib import Path
        qr_path = Path(result['qr_path'])
        if qr_path.exists():
            await update.message.reply_photo(
                photo=open(qr_path, 'rb'),
                caption=f"📱 QR code for `{username}`",
                parse_mode="Markdown"
            )
        
        # Send config file (keep forever)
        config_path = Path(result['config_path'])
        if config_path.exists():
            await update.message.reply_document(
                document=open(config_path, 'rb'),
                filename=f"{username}.conf",
                caption=f"📄 Config file for `{username}`",
                parse_mode="Markdown"
            )
            
    except Exception as e:
        await msg.edit_text(f"❌ Error creating user: {str(e)}")
        asyncio.create_task(auto_delete_message(msg))
    
    # Delete command message
    asyncio.create_task(auto_delete_message(update.message, 5))


async def list_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        msg = await update.message.reply_text(f"⛔ Access denied. Chat ID: `{update.effective_chat.id}`", parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg, 60))
        return
    
    users = wg_manager.list_users()
    
    if not users:
        msg = await update.message.reply_text("📋 No users found")
        asyncio.create_task(auto_delete_message(msg))
        asyncio.create_task(auto_delete_message(update.message, 5))
        return
    
    response = "📋 *WireGuard Users*\n\n"
    for user in users:
        response += f"• `{user}`\n"
    
    msg = await update.message.reply_text(response, parse_mode="Markdown")
    asyncio.create_task(auto_delete_message(msg))
    asyncio.create_task(auto_delete_message(update.message, 5))


async def delete_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update.effective_chat.id):
        msg = await update.message.reply_text(f"⛔ Access denied. Chat ID: `{update.effective_chat.id}`", parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg, 60))
        return
    
    if not context.args:
        msg = await update.message.reply_text("Usage: /delete\\_user <username>", parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(msg))
        asyncio.create_task(auto_delete_message(update.message, 5))
        return
    
    username = context.args[0]
    msg = await update.message.reply_text(f"🗑 Deleting user `{username}`...", parse_mode="Markdown")
    
    try:
        result = wg_manager.delete_user(username)
        await msg.edit_text(f"✅ User `{username}` deleted successfully", parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error deleting user: {str(e)}")
    
    asyncio.create_task(auto_delete_message(msg))
    asyncio.create_task(auto_delete_message(update.message, 5))


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_authorized(query.message.chat_id):
        await query.edit_message_text(f"⛔ Access denied. Chat ID: `{query.message.chat_id}`", parse_mode="Markdown")
        return
    
    data = query.data
    
    if data == "restart_all":
        await query.edit_message_text("🔄 Restarting all tunnels...")
        internal_result, external_result = wg_manager.restart_all()
        
        response = "🔄 *Restart Results*\n\n"
        response += f"🏠 *Internal:* {'✅' if internal_result.success else '❌'}\n"
        response += f"🌍 *External:* {'✅' if external_result.success else '❌'}\n"
        
        msg = await query.edit_message_text(response, parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(query.message))
    
    elif data == "restart_internal":
        await query.edit_message_text("🔄 Restarting internal tunnel...")
        result = wg_manager.restart_internal()
        response = f"🏠 *Internal:* {'✅ Restarted' if result.success else '❌ Failed'}"
        await query.edit_message_text(response, parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(query.message))
    
    elif data == "restart_external":
        await query.edit_message_text("🔄 Restarting external tunnel...")
        result = wg_manager.restart_external()
        response = f"🌍 *External:* {'✅ Restarted' if result.success else '❌ Failed'}"
        await query.edit_message_text(response, parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(query.message))
    
    elif data == "status":
        await query.edit_message_text("📊 Getting status...")
        internal = wg_manager.get_status_internal()
        external = wg_manager.get_status_external()
        
        response = "📊 *Status*\n\n"
        response += f"🏠 Internal: {'✅ UP' if internal.success else '❌ DOWN'}\n"
        response += f"🌍 External: {'✅ UP' if external.success else '❌ DOWN'}"
        
        await query.edit_message_text(response, parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(query.message))
    
    elif data == "list_users":
        users = wg_manager.list_users()
        if not users:
            await query.edit_message_text("📋 No users found")
        else:
            response = "📋 *Users*\n\n"
            for user in users:
                response += f"• `{user}`\n"
            await query.edit_message_text(response, parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(query.message))
    
    elif data == "create_user_prompt":
        await query.edit_message_text(
            "👤 To create a user, send:\n`/create_user <username>`",
            parse_mode="Markdown"
        )
        asyncio.create_task(auto_delete_message(query.message))
    
    elif data == "delete_user_prompt":
        users = wg_manager.list_users()
        if not users:
            await query.edit_message_text("📋 No users to delete")
        else:
            response = "🗑 To delete a user, send:\n`/delete_user <username>`\n\n*Users:*\n"
            for user in users:
                response += f"• `{user}`\n"
            await query.edit_message_text(response, parse_mode="Markdown")
        asyncio.create_task(auto_delete_message(query.message))


def setup_handlers(app: Application):
    """Setup all command and callback handlers."""
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("restart", restart_command))
    app.add_handler(CommandHandler("restart_internal", restart_internal_command))
    app.add_handler(CommandHandler("restart_external", restart_external_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("create_user", create_user_command))
    app.add_handler(CommandHandler("delete_user", delete_user_command))
    app.add_handler(CommandHandler("list_users", list_users_command))
    app.add_handler(CallbackQueryHandler(button_callback))


async def start_bot():
    """Start the Telegram bot (polling mode)."""
    global application
    
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured, bot disabled")
        return
    
    # If webhook URL is configured, don't start polling - webhook mode will be used
    if settings.telegram_webhook_url:
        logger.info("Webhook URL configured, bot will run in webhook mode")
        return
    
    application = Application.builder().token(settings.telegram_bot_token).build()
    setup_handlers(application)

    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    
    logger.info("Telegram bot started in polling mode")

    while True:
        await asyncio.sleep(1)


async def start_bot_webhook() -> Application:
    """Initialize bot for webhook mode (called from FastAPI)."""
    global application
    
    if not settings.telegram_bot_token:
        logger.warning("Telegram bot token not configured, bot disabled")
        return None
    
    application = Application.builder().token(settings.telegram_bot_token).build()
    setup_handlers(application)
    
    await application.initialize()
    await application.start()
    
    # Set webhook with Telegram
    webhook_url = settings.telegram_webhook_url.rstrip('/') + settings.telegram_webhook_path
    await application.bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"]
    )
    
    logger.info(f"Telegram bot started in webhook mode: {webhook_url}")
    return application


async def process_webhook_update(update_data: dict):
    """Process incoming webhook update from Telegram."""
    global application
    
    if not application:
        logger.error("Application not initialized")
        return
    
    update = Update.de_json(update_data, application.bot)
    await application.process_update(update)


async def stop_bot():
    global application
    
    if application:
        # Remove webhook if it was set
        if settings.telegram_webhook_url:
            try:
                await application.bot.delete_webhook()
                logger.info("Webhook removed")
            except Exception as e:
                logger.warning(f"Failed to remove webhook: {e}")
        else:
            await application.updater.stop()
        
        await application.stop()
        await application.shutdown()
        logger.info("Telegram bot stopped")


if __name__ == "__main__":
    import asyncio
    asyncio.run(start_bot())
