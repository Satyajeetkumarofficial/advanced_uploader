from pyrogram.client import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from config import FORCE_SUB_CHANNEL


async def ensure_forcesub(app: Client, message: Message) -> bool:
    """
    True = user allowed
    False = force subscribe message sent, handler ko return karna hai.
    """
    if not FORCE_SUB_CHANNEL:
        return True

    try:
        await app.get_chat_member(FORCE_SUB_CHANNEL, message.from_user.id)
        return True
    except UserNotParticipant:
        channel = FORCE_SUB_CHANNEL.lstrip("@")
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📢 Join Channel",
                        url=f"https://t.me/{channel}",
                    )
                ]
            ]
        )
        await message.reply_text(
            "🚫 Pehle hamare official channel join karo, fir bot use kar sakte ho.",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        return False
    except Exception:
        # Agar kuch aur error ho jaye (bot not admin etc.) to force sub skip
        return True
