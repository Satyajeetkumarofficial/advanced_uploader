import os
import time
from pyrogram.client import Client
from pyrogram.types import Message, InputMediaPhoto

from utils.progress import edit_progress_message, human_readable
from utils.downloader import is_video_ext
from utils.media_tools import generate_screenshots, generate_sample_clip, get_media_duration
from config import MAX_FILE_SIZE, LOG_CHANNEL, PROGRESS_UPDATE_INTERVAL
from database import get_user_doc, increment_usage, update_stats


async def upload_with_thumb_and_progress(
    app: Client,
    message: Message,
    path: str,
    user_id: int,
    progress_msg: Message,
    job_thumb_path: str | None = None,
):
    file_size = os.path.getsize(path)
    if file_size > MAX_FILE_SIZE:
        await message.reply_text("❌ File Telegram limit se badi hai, upload nahi ho sakti.")
        os.remove(path)
        return

    user = get_user_doc(user_id)
    base_name = os.path.basename(path)

    prefix = user.get("prefix") or ""
    suffix = user.get("suffix") or ""
    final_name = f"{prefix}{base_name}{suffix}"

    upload_type = user.get("upload_type", "video")  # "video" / "document"

    caption_template = user.get("caption")
    if caption_template:
        caption = caption_template.replace("{file_name}", final_name)
    else:
        caption = f"📁 `{final_name}`"

    # Thumbnail priority:
    # 1) job_thumb_path (YouTube / yt-dlp)
    # 2) user ka permanent thumb
    # 3) agar upload_type == "video" & file video hai → auto frame se thumb
    thumb_path = None
    thumb_downloaded_path = None
    auto_thumb_dir = None

    if job_thumb_path and os.path.exists(job_thumb_path):
        thumb_path = job_thumb_path
    elif user.get("thumb_file_id"):
        try:
            thumb_downloaded_path = await app.download_media(
                user["thumb_file_id"], file_name=f"thumb_{user_id}.jpg"
            )
            thumb_path = thumb_downloaded_path
        except Exception:
            thumb_path = None

    # AUTO THUMB (agar abhi bhi thumb nahi hai aur video file hai)
    if thumb_path is None and upload_type == "video" and is_video_ext(path):
        auto_thumb_dir = f"auto_thumb_{user_id}"
        shots = generate_screenshots(path, out_dir=auto_thumb_dir, count=1)
        if shots:
            thumb_path = shots[0]

    spoiler_flag = bool(user.get("spoiler"))

    # 📸 Screenshots album (sirf jab file video-type ho)
    if user.get("send_screenshots") and is_video_ext(path):
        from_dir = f"screens_{user_id}"
        shots = generate_screenshots(path, out_dir=from_dir, count=3)
        if shots:
            media = []
            for i, s in enumerate(shots):
                if i == 0:
                    media.append(
                        InputMediaPhoto(
                            s,
                            caption="📸 Video screenshots",
                            has_spoiler=spoiler_flag,
                        )
                    )
                else:
                    media.append(InputMediaPhoto(s, has_spoiler=spoiler_flag))
            try:
                await app.send_media_group(
                    chat_id=message.chat.id,
                    media=media,
                )
            except Exception:
                pass
            finally:
                for s in shots:
                    if os.path.exists(s):
                        os.remove(s)
                try:
                    os.rmdir(from_dir)
                except Exception:
                    pass

    # 🎬 Sample clip (sirf video files)
    if user.get("send_sample") and is_video_ext(path):
        sample_duration = int(user.get("sample_duration") or 15)
        sample_path = f"sample_{user_id}.mp4"
        sample = generate_sample_clip(path, sample_path, sample_duration)
        if sample and os.path.exists(sample):
            try:
                await app.send_video(
                    chat_id=message.chat.id,
                    video=sample,
                    caption=f"🎬 Sample clip ({sample_duration}s)",
                    thumb=thumb_path,
                    has_spoiler=spoiler_flag,
                    supports_streaming=True,
                )
            except Exception:
                pass
            finally:
                if os.path.exists(sample):
                    os.remove(sample)

    await message.reply_text("📤 Upload start ho raha hai...")

    start_time = time.time()
    last_edit = start_time

    async def upload_progress(current, total):
        nonlocal last_edit
        now = time.time()
        if now - last_edit < PROGRESS_UPDATE_INTERVAL:
            return
        elapsed = now - start_time
        speed = current / elapsed if elapsed > 0 else 0
        eta = (total - current) / speed if speed > 0 and total > 0 else None
        last_edit = now
        await edit_progress_message(
            progress_msg,
            "📤 Uploading...",
            current,
            total,
            speed,
            eta,
        )

    # 🔢 Duration detect (0:00 fix)
    duration = None
    if upload_type == "video" and is_video_ext(path):
        duration = get_media_duration(path)

    sent = None
    try:
        if upload_type == "video":
            video_kwargs = dict(
                chat_id=message.chat.id,
                video=path,
                file_name=final_name,
                caption=caption,
                thumb=thumb_path,
                has_spoiler=spoiler_flag,
                supports_streaming=True,
                progress=upload_progress,
            )
            if duration:
                video_kwargs["duration"] = duration

            try:
                sent = await app.send_video(**video_kwargs)
            except Exception:
                # Agar video upload fail ho (codec/ffmpeg issue) to document fallback
                sent = await app.send_document(
                    chat_id=message.chat.id,
                    document=path,
                    file_name=final_name,
                    caption=caption,
                    progress=upload_progress,
                )
        else:
            sent = await app.send_document(
                chat_id=message.chat.id,
                document=path,
                file_name=final_name,
                caption=caption,
                progress=upload_progress,
            )

        increment_usage(user_id, file_size)
        update_stats(downloaded=0, uploaded=file_size)

        user = get_user_doc(user_id)
        limit_count = user.get("daily_count_limit", 0)
        limit_size = user.get("daily_size_limit", 0)
        used_c = user.get("used_count_today", 0)
        used_s = user.get("used_size_today", 0)

        count_status = (
            f"{used_c}/{limit_count}" if limit_count and limit_count > 0 else f"{used_c}/∞"
        )
        size_status = (
            f"{human_readable(used_s)}/{human_readable(limit_size)}"
            if limit_size and limit_size > 0
            else f"{human_readable(used_s)}/∞"
        )

        await progress_msg.edit_text(
            "✅ Ho gaya!\n"
            f"📊 Count today: {count_status}\n"
            f"📦 Size today: {size_status}\n"
            f"File size: {human_readable(file_size)}"
        )

        if LOG_CHANNEL != 0:
            try:
                text = (
                    f"📥 New upload\n"
                    f"👤 User: `{user_id}`\n"
                    f"💾 Size: {human_readable(file_size)}\n"
                    f"📄 File: `{final_name}`\n"
                    f"💬 Chat: {message.chat.id}"
                )
                await app.send_message(LOG_CHANNEL, text)
            except Exception:
                pass

            if sent is not None:
                try:
                    await app.copy_message(
                        chat_id=LOG_CHANNEL,
                        from_chat_id=sent.chat.id,
                        message_id=sent.id,
                    )
                except Exception:
                    pass

        return sent

    finally:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

        if thumb_downloaded_path and os.path.exists(thumb_downloaded_path):
            try:
                os.remove(thumb_downloaded_path)
            except Exception:
                pass

        if job_thumb_path and os.path.exists(job_thumb_path):
            try:
                os.remove(job_thumb_path)
            except Exception:
                pass

        if auto_thumb_dir and os.path.exists(auto_thumb_dir):
            try:
                for f in os.listdir(auto_thumb_dir):
                    try:
                        os.remove(os.path.join(auto_thumb_dir, f))
                    except Exception:
                        pass
                os.rmdir(auto_thumb_dir)
            except Exception:
                pass
