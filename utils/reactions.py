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
