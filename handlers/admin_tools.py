from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import Message

from config import ADMIN_IDS
from database import (
    get_user_doc,
    users_col,
    get_users_count,
)


def register_admin_tools_handlers(app: Client):
    """
    Yahan sab admin-only helper commands register ho rahe hain:
      - /refresh_user <user_id>
      - /refresh_all_users
      - /total_users
    """

    # ====================================
    #      SINGLE USER REFRESH
    # ====================================
    @app.on_message(filters.command("refresh_user") & filters.user(ADMIN_IDS))
    async def refresh_user_handler(client: Client, message: Message):
        """
        /refresh_user <user_id>
        -> Ek user ka daily usage reset karega.
        """
        try:
            if len(message.command) < 2:
                return await message.reply_text("⚠️ Usage: /refresh_user user_id")

            try:
                user_id = int(message.command[1])
            except ValueError:
                return await message.reply_text("❌ Invalid user_id. Sirf numbers bhejo.")

            # ensure user exists (agar nahi hai to create ho jayega)
            get_user_doc(user_id)

            today = datetime.utcnow().strftime("%Y-%m-%d")

            users_col.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "used_count_today": 0,
                        "used_size_today": 0,
                        "last_date": today,
                    }
                },
            )

            await message.reply_text(
                f"🔄 User `{user_id}` ka daily usage reset kar diya gaya.\n"
                f"Now → Count: 0 | Size: 0"
            )

        except Exception as e:
            await message.reply_text(f"❌ Error: `{e}`")

    # ====================================
    #      ALL USERS REFRESH (GLOBAL)
    # ====================================
    @app.on_message(filters.command("refresh_all_users") & filters.user(ADMIN_IDS))
    async def refresh_all_users_handler(client: Client, message: Message):
        """
        /refresh_all_users
        -> Sabhi users ka daily usage reset karega.
        """
        try:
            today = datetime.utcnow().strftime("%Y-%m-%d")

            result = users_col.update_many(
                {},
                {
                    "$set": {
                        "used_count_today": 0,
                        "used_size_today": 0,
                        "last_date": today,
                    }
                },
            )

            await message.reply_text(
                "🔄 All users refreshed successfully.\n"
                f"✔️ Total updated users: {result.modified_count}"
            )

        except Exception as e:
            await message.reply_text(f"❌ Error: `{e}`")

    # ====================================
    #       TOTAL USERS COUNT
    # ====================================
    @app.on_message(filters.command("total_users") & filters.user(ADMIN_IDS))
    async def total_users_handler(client: Client, message: Message):
        """
        /total_users
        -> Total registered users count show karega.
        """
        try:
            total = get_users_count()
            await message.reply_text(
                f"👥 Total registered users: {total}"
            )
        except Exception as e:
            await message.reply_text(f"❌ Error: `{e}`")
