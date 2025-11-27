from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_user_doc, is_banned
from config import BOT_USERNAME
from utils.progress import human_readable
from utils.forcesub import ensure_forcesub
from utils.reactions import pick_reaction


def help_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📸 Screenshots ON/OFF", callback_data="settings_screens"),
            ],
            [
                InlineKeyboardButton("🎬 Sample ON/OFF", callback_data="settings_sample"),
            ],
            [
                InlineKeyboardButton("🎞 Upload: Video/Doc", callback_data="settings_upload"),
            ],
            [
                InlineKeyboardButton("🖼 Thumbnail", callback_data="settings_thumb"),
            ],
            [
                InlineKeyboardButton("📝 Caption", callback_data="settings_caption"),
            ],
        ]
    )


def help_text():
    return (
        "🤓 **Advanced URL Uploader Bot – Help**\n\n"
        "🔗 **URL Format**\n"
        "• Normal: `https://example.com/video.mp4`\n"
        "• Rename ke sath: `URL | new_name.mp4`\n\n"
        "📥 **Main Features**\n"
        "• Direct http/https download + yt-dlp deep scan\n"
        "• Quality select (1080p/720p/480p...) where supported\n"
        "• Telegram file/video rename: `/rename new_name.ext` (reply)\n"
        "• Thumbnail, caption, spoiler, screenshots album, sample clip\n"
        "• Daily count + size limit, premium system, cooldown\n"
        "• Upload type: Video ya Document (URL se aaya file)\n\n"
        "🎛 Neeche buttons se quick settings toggle / manage kar sakte ho."
    )


def about_text():
    return (
        "ℹ️ **About This Bot**\n\n"
        f"🤖 Bot: @{BOT_USERNAME}\n"
        "📌 Advanced URL → Telegram Uploader\n\n"
        "✅ Features:\n"
        "• HTTP/HTTPS direct link uploader\n"
        "• YouTube, reels, streaming links via yt-dlp (jahan possible)\n"
        "• Quality choose, rename, thumbnail, caption\n"
        "• Screenshots, sample clip, spoiler effect\n"
        "• Daily limits, premium users, admin panel & broadcast\n\n"
        "Developed for personal/educational use. Public spamming mat karo. 🙂"
    )


def register_start_handlers(app: Client):
    @app.on_message(filters.command("start") & filters.private)
    async def start_cmd(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return

        if not await ensure_forcesub(client, message):
            return

        user = get_user_doc(message.from_user.id)
        limit_c = user.get("daily_count_limit", 0)
        limit_s = user.get("daily_size_limit", 0)
        used_c = user.get("used_count_today", 0)
        used_s = user.get("used_size_today", 0)

        count_status = (
            f"{used_c}/{limit_c}" if limit_c and limit_c > 0 else f"{used_c}/∞"
        )
        size_status = (
            f"{human_readable(used_s)}/{human_readable(limit_s)}"
            if limit_s and limit_s > 0
            else f"{human_readable(used_s)}/∞"
        )

        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("❓ Help", callback_data="open_help"),
                    InlineKeyboardButton("ℹ️ About", callback_data="open_about"),
                ]
            ]
        )

        await message.reply_text(
            f"👋 Welcome {message.from_user.first_name}!\n\n"
            f"Main @{BOT_USERNAME} hoon – ek **Advanced URL Uploader Bot**.\n\n"
            "Aap yaha:\n"
            "• Koi bhi HTTP/HTTPS/YouTube/streaming URL bhejo\n"
            "• Deep scan + Quality select (jahan possible)\n"
            "• Default/Rename choose karo\n"
            "• Thumbnail, Caption, Screenshots, Sample clip set kar sakte ho\n\n"
            "🔗 Example:\n"
            "`https://example.com/video.mp4`\n"
            "`https://example.com/video.mp4 | my_video.mp4`\n\n"
            "👇 Niche buttons se Help & About dekho.\n\n"
            f"📊 Aaj ka status:\n"
            f"• Count: {count_status}\n"
            f"• Size: {size_status}",
            disable_web_page_preview=True,
            reply_markup=kb,
        )

        try:
            await message.react(pick_reaction("start"))
        except Exception:
            pass

    @app.on_message(filters.command("help") & filters.private)
    async def help_cmd(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return

        if not await ensure_forcesub(client, message):
            return

        await message.reply_text(
            help_text(),
            reply_markup=help_keyboard(),
            disable_web_page_preview=True,
        )
        try:
            await message.react(pick_reaction("help"))
        except Exception:
            pass
