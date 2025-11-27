import random

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
    Sirf Telegram ka real reaction lagane ki koshish karega.
    Agar pyrogram / Bot API support nahi kare ya fail ho jaye
    to kuch nahi kare (no reply message).
    """
    emoji = pick_reaction(category)

    try:
        if hasattr(msg, "react"):
            await msg.react(emoji)
    except Exception:
        # environment support nahi kare to silently ignore
        return
