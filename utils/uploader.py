# utils/uploader.py
import os
import time
from pyrogram.client import Client
from pyrogram.types import Message, InputMediaPhoto

from utils.progress import edit_progress_message, human_readable
from utils.downloader import is_video_ext
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

    # ==============================
    #   BASIC CHECKS
    # ==============================
    if not os.path.exists(path):
        await message.reply_text("❌ File not found.")
        return

    file_size = os.path.getsize(path)
    if file_size > MAX_FILE_SIZE:
        await message.reply_text("❌ File Telegram limit se badi hai.")
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

    upload_type = user.get("upload_type", "video")

    # ==============================
    #   CAPTION
    # ==============================
    caption_template = user.get("caption")
    caption = caption_template.replace("{file_name}", final_name) if caption_template else f"📁 `{final_name}`"

    # ==============================
    #   THUMBNAIL
    # ==============================
    thumb_path = None
    thumb_downloaded_path = None
    auto_thumb_dir = None

    if job_thumb_path and os.path.exists(job_thumb_path):
        thumb_path = job_thumb_path

    elif user.get("thumb_file_id"):
        try:
            thumb_downloaded_path = await app.download_media(
                user["thumb_file_id"],
                file_name=f"thumb_{user_id}.jpg"
            )
            thumb_path = thumb_downloaded_path
        except Exception:
            thumb_path = None

    if thumb_path is None and is_video_ext(path):
        auto_thumb_dir = f"/tmp/auto_thumb_{user_id}"
        os.makedirs(auto_thumb_dir, exist_ok=True)
        auto_thumb = os.path.join(auto_thumb_dir, "thumb.jpg")
        t = generate_thumbnail_frame(path, auto_thumb)
        if t and os.path.exists(t):
            thumb_path = t
        else:
            auto_thumb_dir = None

    spoiler_flag = bool(user.get("spoiler"))

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
        eta = (total - current) / speed if speed > 0 else None
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
    #   VIDEO DURATION
    # ==============================
    duration = None
    if is_video_ext(path):
        try:
            ensure_mp4_faststart(path)
        except Exception:
            pass
        try:
            duration = get_media_duration(path)
        except Exception:
            duration = None

    # ==============================
    #   MAIN UPLOAD
    # ==============================
    sent = None
    try:
        if upload_type == "video" and is_video_ext(path):
            try:
                sent = await app.send_video(
                    chat_id=message.chat.id,
                    video=path,
                    caption=caption,
                    file_name=final_name,
                    thumb=thumb_path,
                    supports_streaming=True,
                    has_spoiler=spoiler_flag,
                    duration=duration if duration else None,
                    progress=upload_progress,
                )
            except Exception:
                sent = await app.send_document(
                    chat_id=message.chat.id,
                    document=path,
                    caption=caption,
                    file_name=final_name,
                    thumb=thumb_path,
                    progress=upload_progress,
                )
        else:
            sent = await app.send_document(
                chat_id=message.chat.id,
                document=path,
                caption=caption,
                file_name=final_name,
                thumb=thumb_path,
                progress=upload_progress,
            )

        # ==============================
        #   POST-UPLOAD: SAMPLE + SCREENSHOTS
        # ==============================
        if sent and is_video_ext(path):

            # -------- SAMPLE CLIP --------
            if user.get("send_sample"):
                sample_duration = int(user.get("sample_duration") or 15)
                sample_path = f"/tmp/sample_{user_id}.mp4"

                print("[DEBUG] Generating sample:", sample_path)
                sample = generate_sample_clip(path, sample_path, sample_duration)

                if sample and os.path.exists(sample_path):
                    try:
                        await app.send_video(
                            chat_id=message.chat.id,
                            video=sample_path,
                            caption=f"🎬 Sample clip ({sample_duration}s)",
                            thumb=thumb_path,
                            supports_streaming=True,
                            has_spoiler=spoiler_flag,
                        )
                    except Exception as e:
                        print("Sample send error:", e)
                    finally:
                        try:
                            os.remove(sample_path)
                        except Exception:
                            pass

            # -------- SCREENSHOTS --------
            if user.get("send_screenshots"):
                from_dir = f"/tmp/screens_{user_id}"
                print("[DEBUG] Generating screenshots:", from_dir)

                shots = generate_screenshots(path, out_dir=from_dir, count=6)
                if shots:
                    media = []
                    for i, s in enumerate(shots):
                        media.append(
                            InputMediaPhoto(
                                s,
                                caption="📸 Video screenshots" if i == 0 else None,
                                has_spoiler=spoiler_flag,
                            )
                        )
                    try:
                        await app.send_media_group(message.chat.id, media)
                    except Exception as e:
                        print("Screenshot send error:", e)
                    finally:
                        for s in shots:
                            try:
                                os.remove(s)
                            except Exception:
                                pass
                        try:
                            os.rmdir(from_dir)
                        except Exception:
                            pass

        # ==============================
        #   STATS
        # ==============================
        increment_usage(user_id, file_size)
        update_stats(downloaded=0, uploaded=file_size)

        await progress_msg.edit_text(
            f"✅ Upload complete\n📦 Size: {human_readable(file_size)}"
        )

        if LOG_CHANNEL and sent:
            try:
                await app.copy_message(
                    LOG_CHANNEL,
                    sent.chat.id,
                    sent.id
                )
            except Exception:
                pass

        return sent

    finally:
        # ==============================
        #   CLEANUP
        # ==============================
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

        for p in [thumb_downloaded_path, job_thumb_path]:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

        if auto_thumb_dir and os.path.exists(auto_thumb_dir):
            try:
                for f in os.listdir(auto_thumb_dir):
                    os.remove(os.path.join(auto_thumb_dir, f))
                os.rmdir(auto_thumb_dir)
            except Exception:
                pass
