from pyrogram import Client, filters
from pyrogram.types import Message
from config import ADMIN_IDS
from database.user_db import (
    get_user_doc,
    users_col,
    get_users_count,
)
from datetime import datetime


def register_admin_tools_handlers(app: Client):

    # ====================================
    #      SINGLE USER REFRESH
    # ====================================
    @app.on_message(filters.command("refresh_user") & filters.user(ADMIN_IDS))
    async def refresh_user_handler(client: Client, message: Message):
        try:
            if len(message.command) < 2:
                return await message.reply_text("⚠️ Usage: /refresh_user user_id")

            user_id = int(message.command[1])

            get_user_doc(user_id)

            users_col.update_one(
                {"user_id": user_id},
                {"$set": {
                    "used_count_today": 0,
                    "used_size_today": 0,
                    "last_date": datetime.utcnow().strftime("%Y-%m-%d")
                }}
            )

            await message.reply_text(
                f"🔄 User `{user_id}` ka daily usage reset kar diya gaya.\n"
                f"Now → Count: 0 | Size: 0 MB"
            )

        except Exception as e:
            await message.reply_text(f"❌ Error: {e}")

    # ====================================
    #      ALL USERS REFRESH (GLOBAL)
    # ====================================
    @app.on_message(filters.command("refresh_all_users") & filters.user(ADMIN_IDS))
    async def refresh_all_users_handler(client: Client, message: Message):

        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")

            result = users_col.update_many(
                {},
                {"$set": {
                    "used_count_today": 0,
                    "used_size_today": 0,
                    "last_date": today
                }}
            )

            await message.reply_text(
                f"🔄 *All Users Refreshed Successfully*\n"
                f"✔️ Total Updated Users: `{result.modified_count}`",
                parse_mode="markdown"
            )

        except Exception as e:
            await message.reply_text(f"❌ Error: {e}")

    # ====================================
    #       TOTAL USERS COUNT
    # ====================================
    @app.on_message(filters.command("total_users") & filters.user(ADMIN_IDS))
    async def total_users_handler(client: Client, message: Message):

        try:
            total = get_users_count()
            await message.reply_text(
                f"👥 *Total Registered Users:* `{total}`",
                parse_mode="markdown"
            )
        except Exception as e:
            await message.reply_text(f"❌ Error: {e}")
