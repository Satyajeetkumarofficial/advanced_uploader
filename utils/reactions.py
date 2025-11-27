import random
import asyncio
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


async def react_message(client, msg, category: str = "success", timeout: int = 5):
    """
    Try to add a reaction to `msg` using `msg.react()` (if Pyrogram supports it).
    If that fails, send a small emoji reply and delete it after `timeout` seconds.
    - client: pyrogram Client
    - msg: pyrogram.types.Message (the message to react to)
    - category: reaction category from _REACTIONS
    - timeout: seconds before deleting fallback emoji message
    """
    emoji = pick_reaction(category)
    # 1) try native react (some Pyrogram versions support Message.react)
    try:
        if hasattr(msg, "react"):
            await msg.react(emoji)
            return True
    except Exception:
        # fallthrough to fallback method
        pass

    # 2) fallback — send a short ephemeral message with emoji and delete it later
    try:
        sent = await client.send_message(
            chat_id=msg.chat.id,
            text=emoji,
            reply_to_message_id=msg.id,
            disable_web_page_preview=True,
        )
        # schedule delete
        async def _del():
            await asyncio.sleep(timeout)
            try:
                await sent.delete()
            except Exception:
                pass

        # schedule background task (no await)
        asyncio.create_task(_del())
        return True
    except Exception:
        return False
