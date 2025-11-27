import random
from typing import Optional

_REACTIONS = {
    "start": ["👋", "🤝", "🌟", "🚀", "✨"],
    "help": ["❓", "📚", "🆘", "ℹ️"],
    "url": ["🔗", "🌐", "🛰️", "📡", "🧭"],
    "success": ["✅", "✔️", "😎", "🤩", "👍", "🙌"],
    "settings": ["⚙️", "🛠️", "🔧", "🎛️", "🧩"],
    "rename": ["✏️", "📝", "✒️", "🔤"],
    "error": ["❌", "⚠️", "🚫", "💥"],
}


def pick_reaction(category: str) -> str:
    emojis = _REACTIONS.get(category)
    if not emojis:
        emojis = ["✅", "👍", "😎"]
    return random.choice(emojis)


async def react_message(client, msg, category: str = "success") -> None:
    """
    Pehle koshish karega real Telegram reaction (msg.react) lagane ki.
    Agar support nahi hua / fail hua to user ke message par stylish emoji ka reply bhej dega.
    """
    emoji = pick_reaction(category)

    # 1) Native message.react() (agar pyrogram + Bot API support kare)
    try:
        if hasattr(msg, "react"):
            await msg.react(emoji)
            return
    except Exception:
        pass

    # 2) Fallback – normal emoji reply
    try:
        await client.send_message(
            chat_id=msg.chat.id,
            text=emoji,
            reply_to_message_id=msg.id,
            disable_web_page_preview=True,
        )
    except Exception:
        pass
