import os
import re
import time
import requests
from urllib.parse import urlparse, parse_qs

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
    is_video_ext,
)
from utils.uploader import upload_with_thumb_and_progress
from utils.progress import human_readable
from config import MAX_FILE_SIZE, NORMAL_COOLDOWN_SECONDS
from handlers.start import help_text, help_keyboard, about_text
from utils.forcesub import ensure_forcesub
from utils.reactions import react_message

# simple URL regex
URL_REGEX = r"https?://[^\s]+"

# per-user pending job state (URL download)
PENDING_DOWNLOAD: dict[int, dict] = {}

# thumbnail ke liye pending photo state
THUMB_PENDING: dict[int, bool] = {}


# ---------------------- helpers ---------------------- #
def split_url_and_name(text: str):
    """
    "url | new_name.mp4" format ko split karta hai.
    """
    parts = text.split("|", 1)
    url_part = parts[0].strip()
    custom_name = parts[1].strip() if len(parts) > 1 else None
    return url_part, custom_name


def safe_filename(name: str) -> str:
    """
    Invalid filesystem chars hata deta hai.
    """
    name = "".join(c for c in name if c not in "\\/:*?\"<>|")
    return name or "file"


def is_ytdlp_site(url: str) -> bool:
    """
    Abhi ke liye sab URLs ko yt-dlp try karne do.
    """
    return True


def build_quality_keyboard(formats):
    """
    Yt-dlp formats se quality buttons banata hai.
    """
    buttons = []
    for f in formats:
        h = f.get("height") or "?"
        size_str = human_readable(f.get("filesize")) if f.get("filesize") else "?"
        buttons.append(
            [
                InlineKeyboardButton(
                    f"{h}p {f.get('ext', '')} ({size_str})",
                    callback_data=f"fmt_{f['format_id']}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton("🌐 Direct URL se try karo", callback_data="direct_dl")]
    )
    return InlineKeyboardMarkup(buttons)


def extract_youtube_id(url: str) -> str | None:
    """
    YouTube / Shorts / youtu.be se video-id nikalta hai.
    """
    try:
        u = urlparse(url)
        host = (u.netloc or "").lower()

        # youtu.be/<id>
        if "youtu.be" in host:
            vid = u.path.lstrip("/")
            return vid or None

        # youtube.com/watch?v=<id>
        if "youtube.com" in host:
            qs = parse_qs(u.query)
            if "v" in qs and qs["v"]:
                return qs["v"][0]

            # youtube.com/shorts/<id>
            if u.path.startswith("/shorts/"):
                return u.path.split("/shorts/")[-1].split("/")[0] or None

            # youtube.com/embed/<id>
            if u.path.startswith("/embed/"):
                return u.path.split("/embed/")[-1].split("/")[0] or None

    except Exception:
        return None
    return None


def get_site_thumbnail_url(info: dict | None, url: str) -> str | None:
    """
    YouTube ke liye hamesha img.youtube.com se JPEG thumbnail,
    baaki sites ke liye info["thumbnail"] try karega.
    """
    yt_id = extract_youtube_id(url)
    if yt_id:
        # high quality YT JPEG thumbnail
        return f"https://img.youtube.com/vi/{yt_id}/maxresdefault.jpg"

    if info:
        return info.get("thumbnail")
    return None


# ---------------------- register handlers ---------------------- #
def register_url_handlers(app: Client):
    # ==============================
    #   THUMBNAIL PHOTO HANDLER
    # ==============================
    @app.on_message(filters.private & filters.photo)
    async def thumb_photo_handler(client: Client, message: Message):
        user_id = message.from_user.id

        # Agar user se thumbnail expected hi nahi hai to ignore
        if not THUMB_PENDING.get(user_id):
            return

        if not message.photo:
            return

        photo = message.photo[-1]
        file_id = photo.file_id

        # DB me save karo
        set_thumb(user_id, file_id)

        # pending state clear
        THUMB_PENDING.pop(user_id, None)

        await message.reply_text(
            "✅ Thumbnail set ho gaya.\n"
            "Ab se aapke VIDEO uploads me ye thumbnail use hoga "
            "(agar YouTube ka original thumbnail ya koi aur override na ho)."
        )

        try:
            await react_message(client, message, "settings")
        except Exception:
            pass

    # ==============================
    #   MAIN URL MESSAGE HANDLER
    # ==============================
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

        # banned
        if is_banned(user_id):
            return

        # force subscribe
        if not await ensure_forcesub(client, message):
            return

        user = get_user_doc(user_id)
        text = message.text.strip()

        # =========================
        # 1) RENAME NAME MODE
        # =========================
        state = PENDING_DOWNLOAD.get(user_id)
        if state and state.get("mode") == "await_new_name":
            # agar user ne naya URL bhej diya → purana rename mode cancel
            if re.search(URL_REGEX, text):
                del PENDING_DOWNLOAD[user_id]
            else:
                new_name = safe_filename(text)
                orig_filename = (
                    state.get("filename") or state.get("title") or "video.mp4"
                )
                _, orig_ext = os.path.splitext(orig_filename)
                if "." not in new_name:
                    if orig_ext:
                        new_name = new_name + orig_ext
                    else:
                        new_name = new_name + ".mp4"

                state["custom_name"] = new_name
                state["filename"] = new_name

                # yt-dlp case → ab quality choose
                if state["type"] == "yt":
                    formats = state["formats"]
                    txt = (
                        "✅ File name set ho gaya.\n\n"
                        f"📄 File: `{state['filename']}`\n\n"
                        "🎥 Ab quality select karo:"
                    )
                    await message.reply_text(
                        txt,
                        reply_markup=build_quality_keyboard(formats),
                    )
                    state["mode"] = "await_quality"
                    try:
                        await react_message(client, message, "rename")
                    except Exception:
                        pass
                    return

                # direct case → straight download
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
                            await react_message(client, message, "success")
                        except Exception:
                            pass
                    except Exception as e:
                        await message.reply_text(f"❌ Error: `{e}`")
                    finally:
                        if user_id in PENDING_DOWNLOAD:
                            del PENDING_DOWNLOAD[user_id]
                    return

        # =========================
        # 2) NORMAL URL HANDLING
        # =========================
        url_candidate, custom_name = split_url_and_name(text)
        match = re.search(URL_REGEX, url_candidate)
        if not match:
            # random text → ignore (koi warning nahi)
            return

        url = match.group(0)

        try:
            await react_message(client, message, "url")
        except Exception:
            pass

        # cooldown for normal users
        if not user.get("is_premium", False) and NORMAL_COOLDOWN_SECONDS > 0:
            last_ts = user.get("last_upload_ts") or 0
            now = time.time()
            diff = now - last_ts
            if last_ts > 0 and diff < NORMAL_COOLDOWN_SECONDS:
                wait_left = int(NORMAL_COOLDOWN_SECONDS - diff)
                m, s = divmod(wait_left, 60)
                wait_txt = f"{m}m {s}s" if m > 0 else f"{s}s"
                await message.reply_text(
                    "⏳ Thoda rukna padega.\n"
                    f"Agla upload {wait_txt} baad kar sakte ho.\n"
                    "Premium users ke liye cooldown nahi hota.",
                )
                return

        # daily limits
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

        # ========= 2.1 yt-dlp TRY =========
        try:
            formats, info = get_formats(url) if is_ytdlp_site(url) else ([], None)
        except Exception:
            formats, info = [], None

        if formats:
            title = (
                info.get("title", head_fname or "video")
                if info
                else (head_fname or "video")
            )

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

            # 🔴 YOUTUBE THUMBNAIL FIX: hamesha JPEG URL generate karo
            thumb_url = get_site_thumbnail_url(info, url)

            PENDING_DOWNLOAD[user_id] = {
                "type": "yt",
                "url": url,
                "user_id": user_id,
                "formats": use_formats,
                "title": title,
                "filename": base_name,
                "custom_name": custom_name,
                "head_size": head_size,
                "thumb_url": thumb_url,  # direct_dl + fmt_ dono use karenge
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

        # ========= 2.2 DIRECT FILE MODE =========
        await wait_msg.edit_text("🌐 Direct file download mode...")

        filename = head_fname or url.split("/")[-1] or "file"
        if len(filename) > 64:
            filename = "file_from_url"
        if custom_name:
            filename = custom_name
        filename = safe_filename(filename)

        # HTML / webpage ko block karo (jab tak extension video/document na ho)
        ctype_lower = (head_ctype or "").lower()
        if ctype_lower.startswith("text/html") and not is_video_ext(filename):
            await wait_msg.edit_text(
                "❌ Is URL par sirf **HTML/webpage** mila.\n"
                "Koi direct video/file link detect nahi hua.\n\n"
                "👉 Agar ye streaming site hai to direct player link ya supported "
                "URL try karo (YT, Insta, reel, mp4, m3u8, etc.)."
            )
            return

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

    # ==============================
    #   CALLBACK HANDLER
    # ==============================
    @app.on_callback_query()
    async def callbacks(client: Client, query):
        data = query.data
        msg = query.message
        chat_id = msg.chat.id
        user_id = query.from_user.id

        try:
            await query.answer()
        except Exception:
            pass

        # ------- HELP / ABOUT MAIN BUTTONS -------
        if data == "open_help":
            await msg.reply_text(
                help_text(),
                reply_markup=help_keyboard(),
                disable_web_page_preview=True,
            )
            try:
                await react_message(client, msg, "help")
            except Exception:
                pass
            return

        if data == "open_about":
            await msg.reply_text(
                about_text(),
                disable_web_page_preview=True,
            )
            try:
                await react_message(client, msg, "help")
            except Exception:
                pass
            return

        # ==========================
        #  SETTINGS SUBMENU
        # ==========================
        if data.startswith("settings_"):
            user = get_user_doc(user_id)

            # 📸 Screenshots ON / OFF
            if data == "settings_screens":
                new_val = not bool(user.get("send_screenshots"))
                set_screenshots(user_id, new_val)

                status_txt = (
                    "📸 Screenshots ab **ON** hain."
                    if new_val
                    else "📸 Screenshots ab **OFF** hain."
                )
                await msg.reply_text(status_txt, disable_web_page_preview=True)

                try:
                    await query.answer(
                        "📸 Screenshots: ON" if new_val else "📸 Screenshots: OFF",
                        show_alert=False,
                    )
                except Exception:
                    pass
                try:
                    await react_message(client, msg, "settings")
                except Exception:
                    pass
                return

            # 🎬 Sample video ON / OFF
            if data == "settings_sample":
                new_val = not bool(user.get("send_sample"))
                # duration None rehne do, user /setsample se set kare
                set_sample(user_id, new_val, None)

                status_txt = (
                    "🎬 Sample video ab **ON** hai."
                    if new_val
                    else "🎬 Sample video ab **OFF** hai."
                )
                await msg.reply_text(status_txt, disable_web_page_preview=True)

                try:
                    await query.answer(
                        "🎬 Sample: ON" if new_val else "🎬 Sample: OFF",
                        show_alert=False,
                    )
                except Exception:
                    pass
                try:
                    await react_message(client, msg, "settings")
                except Exception:
                    pass
                return

            # 🎞 Upload type toggle (VIDEO / DOCUMENT)
            if data == "settings_upload":
                cur = user.get("upload_type", "video")
                new_type = "document" if cur == "video" else "video"
                set_upload_type(user_id, new_type)

                if new_type == "video":
                    status_txt = (
                        "🎞 Upload type ab **VIDEO** hai.\n"
                        "Ab files Telegram me **video ke roop me** jayengi "
                        "(duration + thumbnail ke saath, streamable)."
                    )
                    pretty = "VIDEO (streamable)"
                else:
                    status_txt = (
                        "📄 Upload type ab **DOCUMENT** hai.\n"
                        "Ab files Telegram me **document file** ke roop me jayengi."
                    )
                    pretty = "DOCUMENT (file)"

                await msg.reply_text(status_txt, disable_web_page_preview=True)

                try:
                    await query.answer(
                        f"🎞 Upload type: {pretty}",
                        show_alert=False,
                    )
                except Exception:
                    pass
                try:
                    await react_message(client, msg, "settings")
                except Exception:
                    pass
                return

            # 🖼 Thumbnail settings entry
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
                    await msg.reply_text("🖼 Thumbnail options:", reply_markup=kb)
                else:
                    kb = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "📸 Set Thumbnail", callback_data="thumb_set"
                                )
                            ]
                        ]
                    )
                    await msg.reply_text(
                        "🖼 Aapne abhi koi thumbnail set nahi kiya hai.\n"
                        "Neeche button se set karne ka tarika dekho:",
                        reply_markup=kb,
                    )
                try:
                    await react_message(client, msg, "settings")
                except Exception:
                    pass
                return

            # 📝 Caption settings entry
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
                    await msg.reply_text("📝 Caption options:", reply_markup=kb)
                else:
                    kb = InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    "📝 Set Caption", callback_data="caption_set"
                                )
                            ]
                        ]
                    )
                    await msg.reply_text(
                        "📝 Aapne abhi koi caption set nahi kiya hai.\n"
                        "Neeche button se set karne ka tarika dekho:",
                        reply_markup=kb,
                    )
                try:
                    await react_message(client, msg, "settings")
                except Exception:
                    pass
                return

            return

        # -------- Thumbnail submenu extra actions --------
        if data == "thumb_set":
            THUMB_PENDING[user_id] = True
            await msg.reply_text(
                "📸 Thumbnail set karne ke liye ab koi **photo bhejo**.\n\n"
                "⚠️ Jo **agla photo** bhejoge, wahi thumbnail ban jayega."
            )
            try:
                await react_message(client, msg, "settings")
            except Exception:
                pass
            return

        if data == "thumb_view":
            user = get_user_doc(user_id)
            if not user.get("thumb_file_id"):
                await msg.reply_text("❌ Aapne koi thumbnail set nahi kiya hai.")
                return
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔁 Change", callback_data="thumb_change"
                        ),
                        InlineKeyboardButton(
                            "🗑 Delete", callback_data="thumb_delete"
                        ),
                    ]
                ]
            )
            await client.send_photo(
                chat_id=chat_id,
                photo=user["thumb_file_id"],
                caption="🖼 Ye aapka current thumbnail hai.",
                reply_markup=kb,
            )
            try:
                await react_message(client, msg, "settings")
            except Exception:
                pass
            return

        if data == "thumb_change":
            THUMB_PENDING[user_id] = True
            await msg.reply_text(
                "🔁 Naya thumbnail set karne ke liye ab koi **photo bhejo**.\n\n"
                "⚠️ Jo **agla photo** bhejoge, wahi naya thumbnail ban jayega."
            )
            try:
                await react_message(client, msg, "settings")
            except Exception:
                pass
            return

        if data == "thumb_delete":
            set_thumb(user_id, None)
            THUMB_PENDING.pop(user_id, None)
            await msg.reply_text("✅ Thumbnail delete ho gaya.")
            try:
                await react_message(client, msg, "settings")
            except Exception:
                pass
            return

        # -------- Caption submenu extra actions --------
        if data == "caption_set":
            await msg.reply_text(
                "📝 Caption set karne ke liye `/setcaption mera caption {file_name}` use karo.\n"
                "Example: `/setcaption 🔥 Best Video {file_name}`"
            )
            try:
                await react_message(client, msg, "settings")
            except Exception:
                pass
            return

        if data == "caption_view":
            user = get_user_doc(user_id)
            cap = user.get("caption")
            if not cap:
                await msg.reply_text("❌ Aapne koi caption set nahi kiya hai.")
                return
            kb = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🔁 Change", callback_data="caption_change"
                        ),
                        InlineKeyboardButton(
                            "🗑 Delete", callback_data="caption_delete"
                        ),
                    ]
                ]
            )
            await msg.reply_text(f"📝 Current caption:\n\n`{cap}`", reply_markup=kb)
            try:
                await react_message(client, msg, "settings")
            except Exception:
                pass
            return

        if data == "caption_change":
            await msg.reply_text(
                "🔁 Naya caption set karne ke liye `/setcaption mera naya caption {file_name}` bhejo."
            )
            try:
                await react_message(client, msg, "settings")
            except Exception:
                pass
            return

        if data == "caption_delete":
            set_caption(user_id, None)
            await msg.reply_text("✅ Caption delete ho gaya.")
            try:
                await react_message(client, msg, "settings")
            except Exception:
                pass
            return

        # ============================
        #    DOWNLOAD-RELATED CALLBACKS
        # ============================
        state = PENDING_DOWNLOAD.get(user_id)
        if not state:
            await msg.edit_text("⏱ Time out. Dubara URL bhejo.")
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
                f"⛔ Count limit exceed: {used_c}/{limit_c}\nDubara kal try karo."
            )
            del PENDING_DOWNLOAD[user_id]
            return

        remaining_size = None
        if limit_s and limit_s > 0:
            remaining_size = max(limit_s - used_s, 0)

        # -------- name_default ----------
        if data == "name_default":
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
                    await react_message(client, msg, "settings")
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
                if (
                    remaining_size is not None
                    and head_size > 0
                    and head_size > remaining_size
                ):
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
                        await react_message(client, msg, "success")
                    except Exception:
                        pass
                except Exception as e:
                    await msg.edit_text(f"❌ Error: `{e}`")
                finally:
                    if user_id in PENDING_DOWNLOAD:
                        del PENDING_DOWNLOAD[user_id]
                return

        # -------- name_rename ----------
        if data == "name_rename":
            state["mode"] = "await_new_name"
            prompt = await msg.reply_text(
                "✏ Naya file name bhejo (extension ke sath),\n"
                "example: `my_video.mp4`"
            )
            state["rename_prompt_msg_id"] = prompt.id
            try:
                await react_message(client, msg, "rename")
            except Exception:
                pass
            return

        # -------- direct_dl ----------
        if data == "direct_dl":
            state = PENDING_DOWNLOAD.get(user_id)
            if not state:
                await msg.edit_text("⏱ Time out or no pending job. Dubara URL bhejo.")
                return

            progress_msg = await msg.edit_text("⬇️ Direct download try ho raha hai...")

            # YouTube / site thumbnail agar available ho to pahle download karo
            job_thumb_path = None
            thumb_url = state.get("thumb_url")
            if thumb_url:
                try:
                    r = requests.get(thumb_url, stream=True, timeout=10)
                    r.raise_for_status()
                    job_thumb_path = f"yt_thumb_direct_{user_id}.jpg"
                    with open(job_thumb_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 8):
                            if not chunk:
                                continue
                            f.write(chunk)
                except Exception:
                    job_thumb_path = None

            try:
                path, downloaded_bytes = await download_direct_with_progress(
                    state["url"], state["filename"], progress_msg
                )
            except Exception as e:
                await msg.edit_text(f"❌ Direct download fail: `{e}`")
                if job_thumb_path and os.path.exists(job_thumb_path):
                    os.remove(job_thumb_path)
                if user_id in PENDING_DOWNLOAD:
                    del PENDING_DOWNLOAD[user_id]
                return

            file_size = os.path.getsize(path)
            if file_size > MAX_FILE_SIZE:
                await msg.edit_text("❌ File Telegram limit se badi hai, upload nahi ho sakti.")
                try:
                    os.remove(path)
                except Exception:
                    pass
                if job_thumb_path and os.path.exists(job_thumb_path):
                    os.remove(job_thumb_path)
                if user_id in PENDING_DOWNLOAD:
                    del PENDING_DOWNLOAD[user_id]
                return

            if remaining_size is not None and file_size > remaining_size:
                await msg.edit_text(
                    "⛔ Daily size limit exceed ho jayega is file se.\n"
                    f"Remain: {human_readable(remaining_size)}, File: {human_readable(file_size)}"
                )
                try:
                    os.remove(path)
                except Exception:
                    pass
                if job_thumb_path and os.path.exists(job_thumb_path):
                    os.remove(job_thumb_path)
                if user_id in PENDING_DOWNLOAD:
                    del PENDING_DOWNLOAD[user_id]
                return

            update_stats(downloaded=downloaded_bytes, uploaded=0)
            await upload_with_thumb_and_progress(
                client, msg, path, user_id, progress_msg, job_thumb_path=job_thumb_path
            )
            if user_id in PENDING_DOWNLOAD:
                del PENDING_DOWNLOAD[user_id]
            try:
                await react_message(client, msg, "success")
            except Exception:
                pass
            return

        # -------- fmt_<id> (quality select) ----------
        if data.startswith("fmt_"):
            fmt_id = data.split("_", 1)[1]

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

            # YouTube / site original thumbnail – final upload ke liye
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
                await react_message(client, msg, "success")
            except Exception:
                pass
            return
