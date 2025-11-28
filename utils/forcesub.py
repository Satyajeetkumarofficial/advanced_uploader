from pyrogram.client import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from config import FORCE_SUB_CHANNEL


async def ensure_forcesub(app: Client, message: Message) -> bool:
    """
    True  = user allowed
    False = join msg bhej diya, handler ko return kar jaana hai
    """
    # Force-sub off hai to seedha allow
    if not FORCE_SUB_CHANNEL:
        return True

    try:
        chat = FORCE_SUB_CHANNEL  # @username ya invite link ya id

        # Agar username diya hai to pyrogram direct samajh lega
        await app.get_chat_member(chat, message.from_user.id)
        return True

    except UserNotParticipant:
        # User member nahi hai → join karne ko bolo
        channel_link = None

        # 1) @username diya hai
        if isinstance(FORCE_SUB_CHANNEL, str) and FORCE_SUB_CHANNEL.startswith("@"):
            channel_link = f"https://t.me/{FORCE_SUB_CHANNEL.lstrip('@')}"
        # 2) direct invite link diya ho (t.me/+..., https://t.me/joinchat/...)
        elif isinstance(FORCE_SUB_CHANNEL, str) and FORCE_SUB_CHANNEL.startswith("http"):
            channel_link = FORCE_SUB_CHANNEL

        buttons = []
        if channel_link:
            buttons.append(
                [
                    InlineKeyboardButton(
                        "📢 Join Channel",
                        url=channel_link,
                    )
                ]
            )

        kb = InlineKeyboardMarkup(buttons) if buttons else None

        await message.reply_text(
            "🚫 Pehle hamare official channel join karo,\n"
            "fir bot use kar sakte ho. 🙂",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        return False

    except Exception:
        # Yahan koi config / permission issue hai
        try:
            await message.reply_text(
                "⚠️ Force subscribe configuration me problem hai.\n"
                "Please admin se contact karo."
            )
        except Exception:
            pass
        return False
