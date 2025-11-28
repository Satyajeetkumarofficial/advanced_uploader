from pyrogram.client import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from config import FORCE_SUB_CHANNEL


async def ensure_forcesub(app: Client, message: Message) -> bool:
    """
    True  = user allowed (already joined / force-sub disabled)
    False = join message send ho chuka, handler ko yahin return karna hai.
    """
    # Agar force-sub set hi nahi hai to seedha allow
    if not FORCE_SUB_CHANNEL:
        return True

    try:
        chat = FORCE_SUB_CHANNEL  # int ID ya @username, config se aa raha hai

        # yahan agar user member nahi hoga to UserNotParticipant aayega
        await app.get_chat_member(chat, message.from_user.id)
        return True

    except UserNotParticipant:
        # User channel me nahi hai → join karwao
        # Agar username diya hai to link simple se bana sakte hain
        if isinstance(FORCE_SUB_CHANNEL, str) and FORCE_SUB_CHANNEL.startswith("@"):
            channel_link = f"https://t.me/{FORCE_SUB_CHANNEL.lstrip('@')}"
        else:
            # numeric ID hai → normal t.me open nahi banega, isliye simple text
            channel_link = None

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

    except Exception as e:
        # Yahan koi config issue / bot channel me add nahi / access error aa sakti hai
        # Strict force-sub chahiye to yahan bhi block karna better hai:
        try:
            await message.reply_text(
                "⚠️ Force Subscribe configuration me issue hai.\n"
                "Please admin se contact karo."
            )
        except Exception:
            pass
        # Strict mode: user ko allow mat karo
        return False
