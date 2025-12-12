import math
from pyrogram.types import Message

def human_readable(size: int) -> str:
    if not size:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size, 1024))) if size > 0 else 0
    p = math.pow(1024, i)
    s = round(size / p, 2) if p else 0
    return f"{s}{units[i]}"

def format_eta(seconds: int) -> str:
    seconds = int(seconds or 0)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"

async def edit_progress_message(msg: Message, prefix: str, done: int, total: int, speed: float = None, eta: float = None):
    if msg is None:
        return
    try:
        if total and total > 0:
            percent = int(done * 100 / total)
        else:
            percent = 0
        text = f"{prefix} **{percent}%**\n\nDone: {human_readable(done)} / {human_readable(total or 0)}"
        if speed:
            text += f"\nSpeed: {human_readable(int(speed))}/s"
        if eta:
            text += f"\nETA: {format_eta(int(eta))}"
        await msg.edit_text(text)
    except Exception:
        pass
