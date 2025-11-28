# utils/forcesub.py

from pyrogram.client import Client
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from config import FORCE_SUB_CHANNEL

# Har user ke liye last force-sub message ka record:
# { user_id: (chat_id, message_id) }
FORCE_MESSAGES: dict[int, tuple[int, int]] = {}


def _parse_force_chat_id() -> int | str | None:
    """
    FORCE_SUB_CHANNEL ko proper chat_id me convert karta hai.
    - Agar "@channelusername" hai -> "@channelusername" (string hi chalega)
    - Agar "-100xxxxxxxxxx" ya number hai -> int me convert
    """
    if not FORCE_SUB_CHANNEL:
        return None

    chat_id = FORCE_SUB_CHANNEL.strip()

    if chat_id.startswith("@"):
        # public username
        return chat_id

    # numeric id
    try:
        return int(chat_id)
    except ValueError:
        # kuch galat format hai
        return chat_id


async def _build_force_sub_link(app: Client) -> str | None:
    """
    FORCE_SUB_CHANNEL se proper join link banata hai.
    - Public channel -> t.me/username
    - Private channel -> export_chat_invite_link()
    """
    raw = FORCE_SUB_CHANNEL.strip() if FORCE_SUB_CHANNEL else None
    if not raw:
        return None

    chat_id = _parse_force_chat_id()

    # Agar @username hai
    if isinstance(chat_id, str) and chat_id.startswith("@"):
        return f"https://t.me/{chat_id.lstrip('@')}"

    try:
        chat = await app.get_chat(chat_id)
        if chat.username:
            return f"https://t.me/{chat.username}"

        # Private channel, no username -> invite link
        try:
            invite_link = await app.export_chat_invite_link(chat.id)
            return invite_link
        except Exception:
            return None
    except Exception:
        return None


async def _cleanup_old_force_msg(app: Client, user_id: int):
    """
    Agar is user ke liye koi purana force-sub message store hai,
    to usko delete kar de (agar possible ho).
    """
    info = FORCE_MESSAGES.get(user_id)
    if not info:
        return

    chat_id, msg_id = info
    try:
        await app.delete_messages(chat_id=chat_id, message_ids=[msg_id])
    except Exception:
        pass

    FORCE_MESSAGES.pop(user_id, None)


async def ensure_forcesub(app: Client, message: Message) -> bool:
    """
    True = user allowed
    False = force subscribe message bhej diya, handler ko return karna hai.

    Yahi function har jagah use ho raha:
    - /start
    - /help
    - URL handler
    etc.
    """
    if not FORCE_SUB_CHANNEL:
        # Force-sub fully disabled
        return True

    user_id = message.from_user.id
    chat_id = _parse_force_chat_id()
    if chat_id is None:
        # config galat hai
        await message.reply_text(
            "⚠️ Force subscribe configuration me problem hai.\n"
            "Please admin se contact karo."
        )
        return False

    # Pehle try karo: user already member hai kya?
    try:
        await app.get_chat_member(chat_id, user_id)

        # ✅ Member mil gaya:
        # Agar koi purana force-sub message store hai to delete kar do
        await _cleanup_old_force_msg(app, user_id)

        return True

    except UserNotParticipant:
        # ❌ Abhi bhi join nahi kiya hua
        join_link = await _build_force_sub_link(app)
        if not join_link:
            await message.reply_text(
                "⚠️ Force subscribe configuration me problem hai.\n"
                "Please admin se contact karo."
            )
            return False

        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "📢 Channel Join Karo", url=join_link
                    )
                ]
            ]
        )

        sent = await message.reply_text(
            "🚫 Pehle hamare official channel join karo, fir bot use kar sakte ho.\n\n"
            "1️⃣ Channel join karo.\n"
            "2️⃣ Phir `/start` ya apna URL dubara bhejo.\n\n"
            "Bot aapka membership automatic check karega ✅",
            reply_markup=kb,
            disable_web_page_preview=True,
        )

        # Is user ke liye last force-sub message store kar lo
        FORCE_MESSAGES[user_id] = (sent.chat.id, sent.id)
        return False

    except Exception:
        # Agar koi aur error aaya (bot channel me nahi / permissions issue)
        # To force-sub ko silently skip kar do, taki bot at least kaam kare.
        return True
