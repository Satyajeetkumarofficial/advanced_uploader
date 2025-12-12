# utils/uploader.py
import os
import time
from pyrogram.client import Client
from pyrogram.types import Message, InputMediaPhoto

from utils.progress import edit_progress_message, human_readable
from utils.downloader import is_video_ext   # <-- IMPORTANT
from utils.media_tools import (
    generate_screenshots,
    generate_sample_clip,
    get_media_duration,
    generate_thumbnail_frame,
    ensure_mp4_faststart,
)
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
    """
    Final uploader:
    - Video ke liye screenshots, sample clip, thumbnail, duration
    - Upload type ke hisaab se:
        * upload_type == "video"  -> sirf video files send_video() se
        * upload_type == "document" -> sab send_document() se
    - Facebook / Insta / YouTube sab yahi logic use karenge, kyunki yaha
      sirf local file aur extension dekha ja raha hai.
    """

    # ==============================
    #   BASIC CHECKS
    # ==============================
    file_size = os.path.getsize(path)
    if file_size > MAX_FILE_SIZE:
        await message.reply_text("❌ File Telegram limit se badi hai, upload nahi ho sakti.")
        try:
            os.remove(path)
        except Exception:
            pass
        return

    user = get_user_doc(user_id)
    base_name = os.path.basename(path)

    prefix = user.get("prefix") or ""
    suffix = user.get("suffix") or ""
    final_name = f"{prefix}{base_name}{suffix}"

    upload_type = user.get("upload_type", "video")  # "video" / "document"

    # ==============================
    #   CAPTION
    # ==============================
    caption_template = user.get("caption")
    if caption_template:
        caption = caption_template.replace("{file_name}", final_name)
    else:
        caption = f"📁 `{final_name}`"

    # ==============================
    #   THUMBNAIL PRIORITY
    #   1) job_thumb_path (YouTube / yt-dlp)
    #   2) user ka permanent thumb (thumb_file_id)
    #   3) auto frame from video (middle frame)
    # ==============================
    thumb_path = None
    thumb_downloaded_path = None
    auto_thumb_dir = None

    # 1) Job-specific thumb (yt-dlp se aaya ho)
    if job_thumb_path and os.path.exists(job_thumb_path):
        thumb_path = job_thumb_path

    # 2) User permanent thumb
    elif user.get("thumb_file_id"):
        try:
            thumb_downloaded_path = await app.download_media(
                user["thumb_file_id"],
                file_name=f"thumb_{user_id}.jpg"
            )
            thumb_path = thumb_downloaded_path
        except Exception:
            thumb_path = None

    # 3) Auto thumbnail (sirf video file par, aur jab upload_type "video" ho)
    if thumb_path is None and is_video_ext(path):
        auto_thumb_dir = f"auto_thumb_{user_id}"
        os.makedirs(auto_thumb_dir, exist_ok=True)
        auto_thumb = os.path.join(auto_thumb_dir, "thumb.jpg")
        thumb_file = generate_thumbnail_frame(path, auto_thumb)
        if thumb_file and os.path.exists(thumb_file):
            thumb_path = thumb_file
        else:
            auto_thumb_dir = None  # kuch nahi bana, cleanup skip

    spoiler_flag = bool(user.get("spoiler"))

    # ==============================
    #   SCREENSHOTS (sirf video ke liye)
    # ==============================
    if user.get("send_screenshots") and is_video_ext(path):
        from_dir = f"screens_{user_id}"
        shots = generate_screenshots(path, out_dir=from_dir, count=6)
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
                    media.append(
                        InputMediaPhoto(
                            s,
                            has_spoiler=spoiler_flag,
                        )
                    )
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
                        try:
                            os.remove(s)
                        except Exception:
                            pass
                try:
                    os.rmdir(from_dir)
                except Exception:
                    pass

    # ==============================
    #   SAMPLE CLIP (sirf video ke liye)
    # ==============================
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
                    try:
                        os.remove(sample)
                    except Exception:
                        pass

    # ==============================
    #   PROGRESS CALLBACK
    # ==============================
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

    # ==============================
    #   DURATION (sirf video ke liye)
    # ==============================
    duration = None
    if is_video_ext(path):
        # --- auto remux to ensure moov atom at start (faststart) ---
        try:
            _ens_ok = False
            try:
                _ens_ok = ensure_mp4_faststart(path)
                if _ens_ok:
                    print(f"[media_tools] faststart remux applied for {path}")
            except Exception as _e:
                print(f"[media_tools] faststart error: {_e}")
        except Exception:
            _ens_ok = False

        # read duration
        try:
            duration = get_media_duration(path)
        except Exception as _e:
            print(f"[media_tools] get_media_duration error: {_e}")
            duration = None

    sent = None
    try:
        # ======================================
        #   CASE 1: upload_type == "video"
        #   -> sirf VIDEO EXTENSION wale files
        #      send_video se jayenge
        #   Baaki sab document me jayenge.
        # ======================================
        if upload_type == "video":
            if is_video_ext(path):
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
                    # Agar video upload fail ho (codec issue) to document fallback
                    sent = await app.send_document(
                        chat_id=message.chat.id,
                        document=path,
                        file_name=final_name,
                        caption=caption,
                        thumb=thumb_path,
                        progress=upload_progress,
                    )
            else:
                # Video mode hai, lekin ye video file nahi hai -> document ki tarah
                sent = await app.send_document(
                    chat_id=message.chat.id,
                    document=path,
                    file_name=final_name,
                    caption=caption,
                    thumb=thumb_path,
                    progress=upload_progress,
                )

        # ======================================
        #   CASE 2: upload_type == "document"
        #   -> har file document ki tarah jayegi
        #   (mp3, apk, zip, pdf, html sab).
        # ======================================
        else:
            sent = await app.send_document(
                chat_id=message.chat.id,
                document=path,
                file_name=final_name,
                caption=caption,
                thumb=thumb_path,
                progress=upload_progress,
            )

        # ==============================
        #   USAGE + STATS
        # ==============================
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

        # ==============================
        #   LOG CHANNEL
        # ==============================
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
        # ==============================
        #   CLEANUP
        # ==============================
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
