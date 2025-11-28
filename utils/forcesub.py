from pyrogram import Client
from pyrogram.errors import UserNotParticipant, RPCError
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from config import FORCE_SUB_CHANNEL, FORCE_SUB_LINK


def _normalize_channel(chat: str):
    """
    @username, numeric ID, url – sabko normalize kar deta hai.
    """
    if not chat:
        return None

    chat = chat.strip()

    # @username
    if chat.startswith("@"):
        return chat

    # numeric id (-100xxxx)
    if chat.lstrip("-").isdigit():
        return int(chat)

    # t.me/username or t.me/+inviteCode
    if "t.me" in chat:
        return chat  # treat as link

    return chat


async def _build_join_url(app: Client, chat_id):
    """
    Public channel → username → https://t.me/username
    Private channel → invite link auto-generate
    FORCE_SUB_LINK given → highest priority
    """
    # If user provided FORCE_SUB_LINK → always use it
    if FORCE_SUB_LINK and FORCE_SUB_LINK.startswith("http"):
        return FORCE_SUB_LINK

    # If chat is already a full link
    if isinstance(chat_id, str) and "t.me/" in chat_id:
        return chat_id

    # Get chat info
    try:
        chat = await app.get_chat(chat_id)
    except Exception:
        return None

    # Public channel with username
    if chat.username:
        return f"https://t.me/{chat.username}"

    # Private channel: create auto joinchat link
    try:
        invite = await app.create_chat_invite_link(chat_id)
        return invite.invite_link
    except Exception:
        return None


async def ensure_forcesub(app: Client, message: Message) -> bool:
    """
    ForceSubscribe modern v5 — Auto public/private detection + auto invite-link creation.
    """
    raw = FORCE_SUB_CHANNEL
    if not raw:
        return True  # ForceSub disabled

    chat_id = _normalize_channel(raw)

    try:
        # Check membership
        await app.get_chat_member(chat_id, message.from_user.id)
        return True

    except UserNotParticipant:
        # User not joined → Build join button
        join_url = await _build_join_url(app, chat_id)

        kb = None
        if join_url:
            kb = InlineKeyboardMarkup(
                [[InlineKeyboardButton("📢 Join Channel", url=join_url)]]
            )

        await message.reply_text(
            "🚫 Pehle hamare official channel join karo,\n"
            "fir bot use kar sakte ho.",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
        return False

    except RPCError as e:
        # Bot not admin, no permission, invalid ID etc.
        await message.reply_text(
            "⚠️ Force Subscribe configuration me dikkat hai.\n\n"
            "👉 Check list:\n"
            "• Bot ko channel me add karo\n"
            "• Private channel ho to bot ko 'Invite Users' permission do\n"
            "• FORCE_SUB_CHANNEL & FORCE_SUB_LINK check karo\n\n"
            f"Error: `{e}`"
        )
        return False
