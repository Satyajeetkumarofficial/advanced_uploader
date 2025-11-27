from pyrogram import Client, filters
from pyrogram.types import Message
from database import (
    is_admin,
    set_premium,
    set_limits,
    get_user_doc,
    get_users_count,
    get_all_users,
    get_stats,
    ban_user,
    unban_user,
    is_banned,
    get_banlist,
)
from utils.progress import human_readable


def register_admin_handlers(app: Client):
    @app.on_message(filters.command("setpremium"))
    async def admin_setpremium(_, message: Message):
        if not is_admin(message.from_user.id):
            return

        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text(
                "Usage: `/setpremium user_id [count_limit] [size_limit_mb]`", quote=True
            )
            return

        try:
            uid = int(parts[1])
        except ValueError:
            await message.reply_text("user_id galat hai.", quote=True)
            return

        count_limit = None
        size_limit_mb = None
        if len(parts) >= 3 and parts[2].isdigit():
            count_limit = int(parts[2])
        if len(parts) >= 4 and parts[3].isdigit():
            size_limit_mb = int(parts[3])

        user = set_premium(uid, count_limit, size_limit_mb, True)
        await message.reply_text(
            "✅ PREMIUM set:\n"
            f"User: `{uid}`\n"
            f"Count limit: {user['daily_count_limit'] if user['daily_count_limit'] else '∞'}\n"
            f"Size limit: {human_readable(user['daily_size_limit']) if user['daily_size_limit'] else '∞'}",
            quote=True,
        )

    @app.on_message(filters.command("delpremium"))
    async def admin_delpremium(_, message: Message):
        if not is_admin(message.from_user.id):
            return

        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text(
                "Usage: `/delpremium user_id [count_limit] [size_limit_mb]`", quote=True
            )
            return

        try:
            uid = int(parts[1])
        except ValueError:
            await message.reply_text("user_id galat hai.", quote=True)
            return

        count_limit = None
        size_limit_mb = None
        if len(parts) >= 3 and parts[2].isdigit():
            count_limit = int(parts[2])
        if len(parts) >= 4 and parts[3].isdigit():
            size_limit_mb = int(parts[3])

        user = set_premium(uid, count_limit, size_limit_mb, False)
        await message.reply_text(
            "✅ Premium hataya.\n"
            f"User: `{uid}`\n"
            f"Count limit: {user['daily_count_limit'] if user['daily_count_limit'] else '∞'}\n"
            f"Size limit: {human_readable(user['daily_size_limit']) if user['daily_size_limit'] else '∞'}",
            quote=True,
        )

    @app.on_message(filters.command("setlimit"))
    async def admin_setlimit(_, message: Message):
        if not is_admin(message.from_user.id):
            return
        parts = message.text.split()
        if len(parts) < 3:
            await message.reply_text(
                "Usage: `/setlimit user_id count_limit size_limit_mb` (0 = unlimited)",
                quote=True,
            )
            return
        try:
            uid = int(parts[1])
        except ValueError:
            await message.reply_text("user_id galat hai.", quote=True)
            return

        count_limit = int(parts[2]) if parts[2].lstrip("-").isdigit() else None
        size_limit_mb = None
        if len(parts) >= 4 and parts[3].lstrip("-").isdigit():
            size_limit_mb = int(parts[3])

        user = set_limits(uid, count_limit, size_limit_mb)
        await message.reply_text(
            "✅ Limits updated.\n"
            f"User: `{uid}`\n"
            f"Count: {user['daily_count_limit'] if user['daily_count_limit'] else '∞'}\n"
            f"Size: {human_readable(user['daily_size_limit']) if user['daily_size_limit'] else '∞'}",
            quote=True,
        )

    @app.on_message(filters.command("userstats"))
    async def admin_userstats(_, message: Message):
        if not is_admin(message.from_user.id):
            return
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text("Usage: `/userstats user_id`", quote=True)
            return
        try:
            uid = int(parts[1])
        except ValueError:
            await message.reply_text("user_id galat hai.", quote=True)
            return
        user = get_user_doc(uid)
        text = (
            f"👤 User: `{uid}`\n"
            f"Premium: {user.get('is_premium', False)}\n"
            f"Daily count limit: {user.get('daily_count_limit', 0) or '∞'}\n"
            f"Daily size limit: {human_readable(user.get('daily_size_limit', 0)) if user.get('daily_size_limit', 0) else '∞'}\n"
            f"Used today (count): {user.get('used_count_today', 0)}\n"
            f"Used today (size): {human_readable(user.get('used_size_today', 0))}\n"
            f"Last date: {user.get('last_date')}\n"
            f"Thumbnail set: {'Yes' if user.get('thumb_file_id') else 'No'}\n"
            f"Caption set: {'Yes' if user.get('caption') else 'No'}\n"
            f"Upload type: {user.get('upload_type', 'video')}"
        )
        await message.reply_text(text, quote=True)

    @app.on_message(filters.command("users"))
    async def admin_users(_, message: Message):
        if not is_admin(message.from_user.id):
            return
        total = get_users_count()
        await message.reply_text(f"👥 Total registered users: **{total}**", quote=True)

    @app.on_message(filters.command("stats"))
    async def admin_stats(_, message: Message):
        if not is_admin(message.from_user.id):
            return
        s = get_stats()
        text = (
            "📊 Global Stats:\n"
            f"Downloaded: {human_readable(s['downloaded'])}\n"
            f"Uploaded: {human_readable(s['uploaded'])}\n"
            f"Jobs: {s['jobs']}"
        )
        await message.reply_text(text, quote=True)

    @app.on_message(filters.command("botstatus"))
    async def admin_botstatus(_, message: Message):
        if not is_admin(message.from_user.id):
            return
        s = get_stats()
        text = (
            "🤖 Bot Status:\n"
            f"Downloaded: {human_readable(s['downloaded'])}\n"
            f"Uploaded: {human_readable(s['uploaded'])}\n"
            f"Jobs: {s['jobs']}"
        )
        await message.reply_text(text, quote=True)

    @app.on_message(filters.command("ban"))
    async def admin_ban(_, message: Message):
        if not is_admin(message.from_user.id):
            return
        parts = message.text.split(maxsplit=2)
        if len(parts) < 2:
            await message.reply_text("Usage: `/ban user_id [reason]`", quote=True)
            return
        try:
            uid = int(parts[1])
        except ValueError:
            await message.reply_text("user_id galat hai.", quote=True)
            return
        reason = parts[2] if len(parts) >= 3 else None
        ban_user(uid, reason)
        await message.reply_text(
            f"🚫 User `{uid}` banned.\nReason: {reason}", quote=True
        )

    @app.on_message(filters.command("unban"))
    async def admin_unban(_, message: Message):
        if not is_admin(message.from_user.id):
            return
        parts = message.text.split()
        if len(parts) < 2:
            await message.reply_text("Usage: `/unban user_id`", quote=True)
            return
        try:
            uid = int(parts[1])
        except ValueError:
            await message.reply_text("user_id galat hai.", quote=True)
            return
        unban_user(uid)
        await message.reply_text(f"✅ User `{uid}` unbanned.", quote=True)

    @app.on_message(filters.command("banlist"))
    async def admin_banlist(_, message: Message):
        if not is_admin(message.from_user.id):
            return
        banned = get_banlist()
        if not banned:
            await message.reply_text("✅ Abhi koi banned user nahi hai.")
            return
        lines = []
        for b in banned:
            uid = b.get("user_id")
            reason = b.get("reason", "no reason")
            dt = b.get("date")
            lines.append(f"- `{uid}` | {reason} | {dt}")
        text = "🚫 Last banned users:\n\n" + "\n".join(lines)
        await message.reply_text(text)

    @app.on_message(filters.command("broadcast"))
    async def admin_broadcast(_, message: Message):
        if not is_admin(message.from_user.id):
            return
        if not message.reply_to_message:
            await message.reply_text(
                "Broadcast ke liye kisi message par reply karke `/broadcast` bhejo.",
                quote=True,
            )
            return

        msg = message.reply_to_message
        await message.reply_text("🚀 Broadcast start ho gaya...")

        ok = 0
        fail = 0
        for u in get_all_users():
            uid = u["user_id"]
            try:
                await msg.copy(uid)
                ok += 1
            except Exception:
                fail += 1
        await message.reply_text(
            f"✅ Broadcast complete.\nSuccess: {ok}\nFailed: {fail}"
          )
