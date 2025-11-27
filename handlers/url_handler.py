import os
import re
import time
import requests
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_user_doc,
    is_banned,
    update_stats,
    set_screenshots,
    set_sample,
    set_thumb,
    set_caption,
    set_upload_type,
)
from utils.downloader import (
    get_formats,
    download_direct_with_progress,
    download_with_ytdlp,
    head_info,
)
from utils.uploader import upload_with_thumb_and_progress
from utils.progress import human_readable
from config import MAX_FILE_SIZE, NORMAL_COOLDOWN_SECONDS
from handlers.start import help_text, help_keyboard, about_text
from utils.forcesub import ensure_forcesub
from utils.reactions import pick_reaction


URL_REGEX = r"https?://[^\s]+"

# per-user state
PENDING_DOWNLOAD: dict[int, dict] = {}


def split_url_and_name(text: str):
    parts = text.split("|", 1)
    url_part = parts[0].strip()
    custom_name = parts[1].strip() if len(parts) > 1 else None
    return url_part, custom_name


def safe_filename(name: str) -> str:
    name = "".join(c for c in name if c not in "\\/:*?\"<>|")
    return name or "file"


def is_ytdlp_site(url: str) -> bool:
    # yt-dlp bohot saari sites support karta hai, isliye sab pe try
    return True


def build_quality_keyboard(formats):
    buttons = []
    for f in formats:
        h = f["height"] or "?"
        size_str = human_readable(f["filesize"]) if f["filesize"] else "?"
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{h}p {f['ext']} ({size_str})",
                    callback_data=f"fmt_{f['format_id']}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton("🌐 Direct URL se try karo", callback_data="direct_dl")]
    )
    return InlineKeyboardMarkup(buttons)


def register_url_handlers(app: Client):
    @app.on_message(
        filters.private
        & filters.text
        & ~filters.command(
            [
                "start",
                "help",
                "setthumb",
                "delthumb",
                "showthumb",
                "setcaption",
                "delcaption",
                "showcaption",
                "myplan",
                "spoiler_on",
                "spoiler_off",
                "screens_on",
                "screens_off",
                "sample_on",
                "sample_off",
                "setsample",
                "setprefix",
                "setsuffix",
                "rename",
                "setpremium",
                "delpremium",
                "setlimit",
                "userstats",
                "users",
                "stats",
                "botstatus",
                "ban",
                "unban",
                "broadcast",
                "banlist",
            ]
        )
    )
    async def handle_url(client: Client, message: Message):
        user_id = message.from_user.id

        if is_banned(user_id):
            return

        if not await ensure_forcesub(client, message):
            return

        user = get_user_doc(user_id)

        # rename mode?
        state = PENDING_DOWNLOAD.get(user_id)
        if state and state.get("mode") == "await_new_name":
            if (
                message.reply_to_message
                and message.reply_to_message.id == state.get("rename_prompt_msg_id")
            ):
                new_name = message.text.strip()
                if re.search(URL_REGEX, new_name):
                    await message.reply_text(
                        "❗ Abhi rename mode me ho.\n"
                        "Naya file name bhejo, example: `my_video.mp4`",
                        quote=True,
                    )
                    return

                new_name = safe_filename(new_name)
                if not new_name:
                    await message.reply_text(
                        "❗ Sahi file name bhejo, example: `my_video.mp4`",
                        quote=True,
                    )
                    return

                state["custom_name"] = new_name
                state["filename"] = new_name

                if state["type"] == "yt":
                    formats = state["formats"]
                    text = (
                        "✅ File name set ho gaya.\n\n"
                        f"📄 File: `{state['filename']}`\n\n"
                        "🎥 Ab quality select karo:"
                    )
                    await message.reply_text(
                        text, reply_markup=build_quality_keyboard(formats)
                    )
                    state["mode"] = "await_quality"
                    try:
                        await message.react(pick_reaction("rename"))
                    except Exception:
                        pass
                    return

                if state["type"] == "direct":
                    url = state["url"]
                    filename = state["filename"]
                    head_size = state.get("head_size", 0)

                    if head_size > 0 and head_size > MAX_FILE_SIZE:
                        await message.reply_text(
                            f"⛔ File Telegram limit se badi hai.\n"
                            f"Size: {human_readable(head_size)}"
                        )
                        del PENDING_DOWNLOAD[user_id]
                        return

                    progress_msg = await message.reply_text("⬇️ Downloading...")
                    try:
                        path, downloaded_bytes = await download_direct_with_progress(
                            url, filename, progress_msg
                        )
                        file_size = os.path.getsize(path)
                        if file_size > MAX_FILE_SIZE:
                            await message.reply_text(
                                "❌ File Telegram limit se badi hai, upload nahi ho sakti."
                            )
                            os.remove(path)
                            del PENDING_DOWNLOAD[user_id]
                            return

                        update_stats(downloaded=downloaded_bytes, uploaded=0)

                        await upload_with_thumb_and_progress(
                            client, message, path, user_id, progress_msg
                        )
                        try:
                            await message.react(pick_reaction("success"))
                        except Exception:
                            pass
                    except Exception as e:
                        await message.reply_text(f"❌ Error: `{e}`")
                    finally:
                        if user_id in PENDING_DOWNLOAD:
                            del PENDING_DOWNLOAD[user_id]
                    return
            # else: naya normal URL treat hoga

        # naya URL
        text = message.text.strip()
        url_candidate, custom_name = split_url_and_name(text)
        match = re.search(URL_REGEX, url_candidate)
        if not match:
            # URL nahi → koi reply nahi
            return

        url = match.group(0)

        # random URL reaction
        try:
            await message.react(pick_reaction("url"))
        except Exception:
            pass

        # cooldown
        if not user.get("is_premium", False) and NORMAL_COOLDOWN_SECONDS > 0:
            last_ts = user.get("last_upload_ts") or 0
            now = time.time()
            diff = now - last_ts
            if last_ts > 0 and diff < NORMAL_COOLDOWN_SECONDS:
                wait_left = int(NORMAL_COOLDOWN_SECONDS - diff)
                m, s = divmod(wait_left, 60)
                if m > 0:
                    wait_txt = f"{m}m {s}s"
                else:
                    wait_txt = f"{s}s"
                await message.reply_text(
                    "⏳ Thoda rukna padega.\n"
                    f"Agla upload {wait_txt} baad kar sakte ho.\n"
                    "Premium users ke liye cooldown nahi hota.",
                )
                return

        limit_c = user["daily_count_limit"]
        limit_s = user["daily_size_limit"]
        used_c = user["used_count_today"]
        used_s = user["used_size_today"]

        if limit_c and limit_c > 0 and used_c >= limit_c:
            await message.reply_text(
                f"⛔ Aaj ka upload count limit khatam.\n"
                f"Used: {used_c}/{limit_c}\n"
                "Admin se contact karo ya premium ke liye request karo."
            )
            return

        wait_msg = await message.reply_text(
            "🔍 Link deep scan ho raha hai (`HEAD` + `yt-dlp`)..."
        )

        head_size, head_ctype, head_fname = head_info(url)

        remaining_size = None
        if limit_s and limit_s > 0:
            remaining_size = max(limit_s - used_s, 0)

        if head_size > 0:
            if head_size > MAX_FILE_SIZE:
                await wait_msg.edit_text(
                    f"⛔ Single file size bohot bada hai.\n"
                    f"Size: {human_readable(head_size)} (> Telegram limit)"
                )
                return
            if remaining_size is not None and head_size > remaining_size:
                await wait_msg.edit_text(
                    "⛔ Aaj ka **daily size limit** exceed ho jayega is file se.\n"
                    f"Remain: {human_readable(remaining_size)}, File: {human_readable(head_size)}"
                )
                return

        # pehle yt-dlp se sab types video/stream try
        try:
            formats, info = get_formats(url) if is_ytdlp_site(url) else ([], None)
        except Exception:
            formats, info = [], None

        if formats:
            title = info.get("title", head_fname or "video")

            filtered = []
            for f in formats:
                size = f.get("filesize") or 0
                if size and size > MAX_FILE_SIZE:
                    continue
                if remaining_size is not None and size and size > remaining_size:
                    continue
                filtered.append(f)

            use_formats = filtered if filtered else formats

            base_name = custom_name or f"{title}.mp4"
            base_name = safe_filename(base_name)

            thumb_url = info.get("thumbnail")

            PENDING_DOWNLOAD[user_id] = {
                "type": "yt",
                "url": url,
                "user_id": user_id,
                "formats": use_formats,
                "title": title,
                "filename": base_name,
                "custom_name": custom_name,
                "head_size": head_size,
                "thumb_url": thumb_url,
                "mode": "await_name_choice",
            }

            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "✅ Default name", callback_data="name_default"
                        ),
                        InlineKeyboardButton("✏ Rename", callback_data="name_rename"),
                    ]
                ]
            )

            await wait_msg.edit_text(
                "✅ Deep scan complete.\n\n"
                f"🔗 URL: `{url}`\n"
                f"📄 Detected file name:\n`{base_name}`\n\n"
                "Neeche se naam choose karo:",
                reply_markup=kb,
            )
            return

        # direct file
        await wait_msg.edit_text("🌐 Direct file download mode...")

        filename = head_fname or url.split("/")[-1] or "file"
        if len(filename) > 64:
            filename = "file_from_url"
        if custom_name:
            filename = custom_name
        filename = safe_filename(filename)

        PENDING_DOWNLOAD[user_id] = {
            "type": "direct",
            "url": url,
            "user_id": user_id,
            "title": filename,
            "filename": filename,
            "custom_name": custom_name,
            "head_size": head_size,
            "mode": "await_name_choice",
        }

        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Default name", callback_data="name_default"),
                    InlineKeyboardButton("✏ Rename", callback_data="name_rename"),
                ]
            ]
        )

        await wait_msg.edit_text(
            "✅ Deep scan complete.\n\n"
            f"🔗 URL: `{url}`\n"
            f"📄 Detected file name:\n`{filename}`\n\n"
            "Neeche se naam choose karo:",
            reply_markup=kb,
        )

    @app.on_callback_query()
    async def callbacks(client: Client, query):
        data = query.data
        msg = query.message
        chat_id = msg.chat.id
        user_id = query.from_user.id

        # HELP / ABOUT
        if data == "open_help":
            await query.answer()
            await msg.reply_text(
                help_text(),
                reply_markup=help_keyboard(),
                disable_web_page_preview=True,
            )
            try:
                await msg.react(pick_reaction("help"))
            except Exception:
                pass
            return

        if data == "open_about":
            await query.answer()
            await msg.reply_text(
                about_text(),
                disable_web_page_preview=True,
            )
            try:
                await msg.react(pick_reaction("help"))
            except Exception:
                pass
            return

        # SETTINGS (help-menu buttons)
        if data.startswith("settings_"):
            user = get_user_doc(user_id)

            if data == "settings_screens":
                new_val = not bool(user.get("send_screenshots"))
                set_screenshots(user_id, new_val)
                await query.answer(
                    "📸 Screenshots: ON" if new_val else "📸 Screenshots: OFF",
                    show_alert=True,
                )
                try:
                    await msg.react(pick_reaction("settings"))
                except Exception:
                    pass
                return

            if data == "settings_sample":
                new_val = not bool(user.get("send_sample"))
                set_sample(user_id, new_val, None)
                await query.answer(
                    "🎬 Sample: ON" if new_val else "🎬 Sample: OFF",
                    show_alert=True,
                )
                try:
                    await msg.react(pick_reaction("settings"))
                except Exception:
                    pass
                return

            if data == "settings_upload":
                cur = user.get("upload_type", "video")
                new_type = "document" if cur == "video" else "video"
                set_upload_type(user_id, new_type)
                await query.answer(
                    f"🎞 Upload type: {new_type.upper()}",
                    show_alert=True,
                )
                try:
                    await msg.react(pick_reaction("settings"))
                except Exception:
                    pass
                return

            if data == "settings_thumb":
                if user.get("thumb_file_id"):
                    kb = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "👁 View", callback_data="thumb_view"
                                ),
                                InlineKeyboardButton(
                                    "🗑 Delete", callback_data="thumb_delete"
                                ),
                            ]
                        ]
                    )
                    await query.answer()
                    await msg.reply_text(
                        "🖼 Thumbnail options:", reply_markup=kb
                    )
                else:
                    await query.answer(
                        "Thumbnail set nahi hai.\nSet karne ke liye kisi photo par reply karke `/setthumb` bhejo.",
                        show_alert=True,
                    )
                try:
                    await msg.react(pick_reaction("settings"))
                except Exception:
                    pass
                return

            if data == "settings_caption":
                if user.get("caption"):
                    kb = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "👁 View", callback_data="caption_view"
                                ),
                                InlineKeyboardButton(
                                    "🗑 Delete", callback_data="caption_delete"
                                ),
                            ]
                        ]
                    )
                    await query.answer()
                    await msg.reply_text(
                        "📝 Caption options:", reply_markup=kb
                    )
                else:
                    await query.answer(
                        "Caption set nahi hai.\nSet karne ke liye `/setcaption mera caption {file_name}` use karo.",
                        show_alert=True,
                    )
                try:
                    await msg.react(pick_reaction("settings"))
                except Exception:
                    pass
                return

            return

        # Thumbnail submenu
        if data == "thumb_view":
            await query.answer()
            user = get_user_doc(user_id)
            if not user.get("thumb_file_id"):
                await msg.reply_text("❌ Aapne koi thumbnail set nahi kiya hai.")
                return
            await client.send_photo(
                chat_id=chat_id,
                photo=user["thumb_file_id"],
                caption="🖼 Ye aapka current thumbnail hai.",
            )
            try:
                await msg.react(pick_reaction("settings"))
            except Exception:
                pass
            return

        if data == "thumb_delete":
            await query.answer("Thumbnail delete ho gaya.", show_alert=True)
            set_thumb(user_id, None)
            await msg.reply_text("✅ Thumbnail delete ho gaya.")
            try:
                await msg.react(pick_reaction("settings"))
            except Exception:
                pass
            return

        # Caption submenu
        if data == "caption_view":
            await query.answer()
            user = get_user_doc(user_id)
            cap = user.get("caption")
            if not cap:
                await msg.reply_text("❌ Aapne koi caption set nahi kiya hai.")
                return
            await msg.reply_text(f"📝 Current caption:\n\n`{cap}`")
            try:
                await msg.react(pick_reaction("settings"))
            except Exception:
                pass
            return

        if data == "caption_delete":
            await query.answer("Caption delete ho gaya.", show_alert=True)
            set_caption(user_id, None)
            await msg.reply_text("✅ Caption delete ho gaya.")
            try:
                await msg.react(pick_reaction("settings"))
            except Exception:
                pass
            return

        # Niche se download-related callbacks

        state = PENDING_DOWNLOAD.get(user_id)
        if not state:
            await query.answer("⏱ Time out. Dubara URL bhejo.", show_alert=True)
            return

        url = state["url"]
        filename = state["filename"]
        head_size = state.get("head_size", 0)

        user = get_user_doc(user_id)
        limit_c = user["daily_count_limit"]
        limit_s = user["daily_size_limit"]
        used_c = user["used_count_today"]
        used_s = user["used_size_today"]

        if limit_c and limit_c > 0 and used_c >= limit_c:
            await msg.edit_text(
                f"⛔ Count limit exceed: {used_c}/{limit_c}\n" "Dubara kal try karo."
            )
            del PENDING_DOWNLOAD[user_id]
            return

        remaining_size = None
        if limit_s and limit_s > 0:
            remaining_size = max(limit_s - used_s, 0)

        if data == "name_default":
            await query.answer("Default file name use hoga.", show_alert=False)

            if state["type"] == "yt":
                formats = state["formats"]
                await msg.edit_text(
                    "🎥 Video/streaming site detect hui.\n"
                    f"📄 File: `{state['filename']}`\n\n"
                    "Quality select karo:",
                    reply_markup=build_quality_keyboard(formats),
                )
                state["mode"] = "await_quality"
                try:
                    await msg.react(pick_reaction("settings"))
                except Exception:
                    pass
                return

            if state["type"] == "direct":
                if head_size > 0 and head_size > MAX_FILE_SIZE:
                    await msg.edit_text(
                        f"⛔ File Telegram limit se badi hai.\n"
                        f"Size: {human_readable(head_size)}"
                    )
                    del PENDING_DOWNLOAD[user_id]
                    return
                if remaining_size is not None and head_size > 0 and head_size > remaining_size:
                    await msg.edit_text(
                        "⛔ Daily size limit exceed ho jayega is file se.\n"
                        f"Remain: {human_readable(remaining_size)}, File: {human_readable(head_size)}"
                    )
                    del PENDING_DOWNLOAD[user_id]
                    return

                progress_msg = await msg.edit_text("⬇️ Downloading...")
                try:
                    path, downloaded_bytes = await download_direct_with_progress(
                        url, filename, progress_msg
                    )
                    file_size = os.path.getsize(path)
                    if file_size > MAX_FILE_SIZE:
                        await msg.edit_text(
                            "❌ File Telegram limit se badi hai, upload nahi ho sakti."
                        )
                        os.remove(path)
                        del PENDING_DOWNLOAD[user_id]
                        return

                    if remaining_size is not None and file_size > remaining_size:
                        await msg.edit_text(
                            "⛔ Daily size limit exceed ho jayega is file se.\n"
                            f"Remain: {human_readable(remaining_size)}, File: {human_readable(file_size)}"
                        )
                        os.remove(path)
                        del PENDING_DOWNLOAD[user_id]
                        return

                    update_stats(downloaded=downloaded_bytes, uploaded=0)
                    await upload_with_thumb_and_progress(
                        client, msg, path, user_id, progress_msg
                    )
                    try:
                        await msg.react(pick_reaction("success"))
                    except Exception:
                        pass
                except Exception as e:
                    await msg.edit_text(f"❌ Error: `{e}`")
                finally:
                    if user_id in PENDING_DOWNLOAD:
                        del PENDING_DOWNLOAD[user_id]
                return

        if data == "name_rename":
            await query.answer("Naya file name bhejo (ext ke sath).", show_alert=True)
            state["mode"] = "await_new_name"
            prompt = await msg.reply_text(
                "✏ Naya file name bhejo (extension ke sath),\n"
                "example: `my_video.mp4`"
            )
            state["rename_prompt_msg_id"] = prompt.id
            try:
                await msg.react(pick_reaction("rename"))
            except Exception:
                pass
            return

        if data == "direct_dl":
            await query.answer("Direct download try ho raha hai...", show_alert=False)
            progress_msg = await msg.edit_text("⬇️ Direct download try ho raha hai...")
            try:
                path, downloaded_bytes = await download_direct_with_progress(
                    url, filename, progress_msg
                )
            except Exception as e:
                await msg.edit_text(f"❌ Direct download fail: `{e}`")
                if os.path.exists(filename):
                    os.remove(filename)
                del PENDING_DOWNLOAD[user_id]
                return

            file_size = os.path.getsize(path)
            if file_size > MAX_FILE_SIZE:
                await msg.edit_text("❌ File Telegram limit se badi hai, upload nahi ho sakti.")
                os.remove(path)
                del PENDING_DOWNLOAD[user_id]
                return

            if remaining_size is not None and file_size > remaining_size:
                await msg.edit_text(
                    "⛔ Daily size limit exceed ho jayega is file se.\n"
                    f"Remain: {human_readable(remaining_size)}, File: {human_readable(file_size)}"
                )
                os.remove(path)
                del PENDING_DOWNLOAD[user_id]
                return

            update_stats(downloaded=downloaded_bytes, uploaded=0)
            await upload_with_thumb_and_progress(
                client, msg, path, user_id, progress_msg
            )
            del PENDING_DOWNLOAD[user_id]
            try:
                await msg.react(pick_reaction("success"))
            except Exception:
                pass
            return

        if data.startswith("fmt_"):
            fmt_id = data.split("_", 1)[1]
            await query.answer(f"Format: {fmt_id}", show_alert=False)

            formats = state["formats"]
            fmt_size = 0
            for f in formats:
                if f["format_id"] == fmt_id:
                    fmt_size = f.get("filesize") or 0
                    break

            if remaining_size is not None and fmt_size and fmt_size > remaining_size:
                await msg.edit_text(
                    "⛔ Daily size limit exceed ho sakta hai is quality se.\n"
                    f"Remain: {human_readable(remaining_size)}, Format: {human_readable(fmt_size)}"
                )
                del PENDING_DOWNLOAD[user_id]
                return

            await msg.edit_text(
                f"⬇️ `{fmt_id}` quality me download ho raha hai... (yt-dlp)\n"
                f"📄 File: `{filename}`"
            )

            tmp_name = "temp_ytdlp_video"

            try:
                path = download_with_ytdlp(url, fmt_id, tmp_name)
                final_path = filename
                os.replace(path, final_path)
                path = final_path
            except Exception as e:
                await msg.edit_text(f"❌ yt-dlp download fail: `{e}`")
                if os.path.exists(tmp_name):
                    os.remove(tmp_name)
                del PENDING_DOWNLOAD[user_id]
                return

            file_size = os.path.getsize(path)
            if file_size > MAX_FILE_SIZE:
                await msg.edit_text("❌ File Telegram limit se badi hai, upload nahi ho sakti.")
                os.remove(path)
                del PENDING_DOWNLOAD[user_id]
                return

            if remaining_size is not None and file_size > remaining_size:
                await msg.edit_text(
                    "⛔ Daily size limit exceed ho jayega is file se.\n"
                    f"Remain: {human_readable(remaining_size)}, File: {human_readable(file_size)}"
                )
                os.remove(path)
                del PENDING_DOWNLOAD[user_id]
                return

            job_thumb_path = None
            thumb_url = state.get("thumb_url")
            if thumb_url:
                try:
                    r = requests.get(thumb_url, stream=True, timeout=10)
                    r.raise_for_status()
                    job_thumb_path = f"yt_thumb_{user_id}.jpg"
                    with open(job_thumb_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 8):
                            if not chunk:
                                continue
                            f.write(chunk)
                except Exception:
                    job_thumb_path = None

            update_stats(downloaded=0, uploaded=0)
            progress_msg = await msg.edit_text("📤 Upload start ho raha hai...")

            await upload_with_thumb_and_progress(
                client,
                msg,
                path,
                user_id,
                progress_msg,
                job_thumb_path=job_thumb_path,
            )

            del PENDING_DOWNLOAD[user_id]
            try:
                await msg.react(pick_reaction("success"))
            except Exception:
                pass
            return
