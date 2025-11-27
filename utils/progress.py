import math
from pyrogram.types import Message


def human_readable(size: int) -> str:
    if size == 0:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size, 1024)))
    p = math.pow(1024, i)
    s = round(size / p, 2)
    return f"{s}{units[i]}"


def format_eta(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 0:
        seconds = 0
    m, s = divmod(seconds, 60)
    if m == 0:
        return f"{s}s"
    return f"{m}m {s}s"


async def edit_progress_message(
    msg: Message,
    prefix: str,
    done: int,
    total: int,
    speed: float | None = None,
    eta: float | None = None,
):
    if total <= 0:
        percent = 0
    else:
        percent = done * 100 // total

    text = f"{prefix} **{percent}%**\n\nDone: {human_readable(done)} / {human_readable(total)}"

    if speed is not None and speed > 0:
        text += f"\nSpeed: {human_readable(int(speed))}/s"
    if eta is not None and eta > 0:
        text += f"\nETA: {format_eta(eta)}"

    try:
        await msg.edit_text(text)
    except Exception:
        pass
