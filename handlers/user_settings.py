from pyrogram import Client, filters
from pyrogram.types import Message
from utils.progress import human_readable
from database import (
    set_thumb,
    set_caption,
    get_user_doc,
    is_banned,
    set_prefix,
    set_suffix,
    set_spoiler,
    set_screenshots,
    set_sample,
)
from utils.uploader import upload_with_thumb_and_progress
from utils.forcesub import ensure_forcesub
from utils.reactions import pick_reaction


def register_user_settings_handlers(app: Client):
    @app.on_message(filters.command("setthumb") & filters.private)
    async def setthumb_cmd(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return

        if not message.reply_to_message or not message.reply_to_message.photo:
            await message.reply_text(
                "📸 Thumbnail set karne ke liye kisi **photo par reply** karke `/setthumb` bhejo."
            )
            return
        photo = message.reply_to_message.photo
        file_id = photo.file_id
        set_thumb(message.from_user.id, file_id)
        await message.reply_text("✅ Thumbnail save ho gaya.")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("delthumb") & filters.private)
    async def delthumb_cmd(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return
        set_thumb(message.from_user.id, None)
        await message.reply_text("✅ Thumbnail hata diya gaya.")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("showthumb") & filters.private)
    async def showthumb_cmd(app_: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(app_, message):
            return

        user = get_user_doc(message.from_user.id)
        if not user.get("thumb_file_id"):
            await message.reply_text("❌ Aapne koi thumbnail set nahi kiya hai.")
            return
        await app_.send_photo(
            chat_id=message.chat.id,
            photo=user["thumb_file_id"],
            caption="🖼 Ye aapka current thumbnail hai.",
        )
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("setcaption") & filters.private)
    async def setcaption_cmd(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return

        if len(message.text.split(maxsplit=1)) < 2:
            await message.reply_text(
                "Usage:\n`/setcaption mera naya caption {file_name}`\n\n"
                "👉 `{file_name}` jagah par file ka real naam aa jayega."
            )
            return
        caption = message.text.split(maxsplit=1)[1]
        set_caption(message.from_user.id, caption)
        await message.reply_text("✅ Caption save ho gaya.")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("delcaption") & filters.private)
    async def delcaption_cmd(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return

        set_caption(message.from_user.id, None)
        await message.reply_text("✅ Custom caption hata diya gaya.")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("showcaption") & filters.private)
    async def showcaption_cmd(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return

        user = get_user_doc(message.from_user.id)
        cap = user.get("caption")
        if not cap:
            await message.reply_text("❌ Aapne koi caption set nahi kiya hai.")
            return
        await message.reply_text(f"📝 Current caption:\n\n`{cap}`")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("myplan") & filters.private)
    async def myplan_cmd(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return

        user = get_user_doc(message.from_user.id)
        limit_c = user.get("daily_count_limit", 0)
        limit_s = user.get("daily_size_limit", 0)
        used_c = user.get("used_count_today", 0)
        used_s = user.get("used_size_today", 0)

        count_status = (
            f"{used_c}/{limit_c}" if limit_c and limit_c > 0 else f"{used_c}/∞"
        )
        size_status = (
            f"{human_readable(used_s)}/{human_readable(limit_s)}"
            if limit_s and limit_s > 0
            else f"{human_readable(used_s)}/∞"
        )

        text = (
            "📋 Aapka Plan Info:\n\n"
            f"Premium: **{user.get('is_premium', False)}**\n"
            f"Daily count limit: **{limit_c if limit_c else '∞'}**\n"
            f"Daily size limit: **{human_readable(limit_s) if limit_s else '∞'}**\n"
            f"Used today (count): **{used_c}**\n"
            f"Used today (size): **{human_readable(used_s)}**\n"
            f"Last reset (UTC): `{user.get('last_date')}`\n"
            f"Thumbnail set: **{'Yes' if user.get('thumb_file_id') else 'No'}**\n"
            f"Caption set: **{'Yes' if user.get('caption') else 'No'}**\n"
            f"Upload type: **{user.get('upload_type', 'video')}**"
        )
        await message.reply_text(text)
        try:
            await message.react(pick_reaction("help"))
        except Exception:
            pass

    @app.on_message(filters.command("spoiler_on") & filters.private)
    async def spoiler_on(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return
        set_spoiler(message.from_user.id, True)
        await message.reply_text("✅ Spoiler effect ON.")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("spoiler_off") & filters.private)
    async def spoiler_off(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return
        set_spoiler(message.from_user.id, False)
        await message.reply_text("✅ Spoiler effect OFF.")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("screens_on") & filters.private)
    async def screens_on(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return
        set_screenshots(message.from_user.id, True)
        await message.reply_text("✅ Video screenshots ON (3 snaps per video).")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("screens_off") & filters.private)
    async def screens_off(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return
        set_screenshots(message.from_user.id, False)
        await message.reply_text("✅ Video screenshots OFF.")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("sample_on") & filters.private)
    async def sample_on(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return
        set_sample(message.from_user.id, True, None)
        await message.reply_text("✅ Sample clip ON (default 15s).")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("sample_off") & filters.private)
    async def sample_off(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return
        set_sample(message.from_user.id, False, None)
        await message.reply_text("✅ Sample clip OFF.")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("setsample") & filters.private)
    async def set_sample_duration(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            await message.reply_text("Usage: `/setsample 10` (seconds)", quote=True)
            return
        sec = int(parts[1])
        if sec <= 0 or sec > 60:
            await message.reply_text(
                "Sample duration 1–60 seconds ke beech me rakho.", quote=True
            )
            return
        set_sample(message.from_user.id, True, sec)
        await message.reply_text(f"✅ Sample clip ON & duration set to {sec}s.")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("setprefix") & filters.private)
    async def setprefix_cmd(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return
        if len(message.text.split(maxsplit=1)) < 2:
            await message.reply_text("Usage: `/setprefix [text_]`")
            return
        txt = message.text.split(maxsplit=1)[1]
        set_prefix(message.from_user.id, txt)
        await message.reply_text(f"✅ Prefix set: `{txt}`")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("setsuffix") & filters.private)
    async def setsuffix_cmd(client: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(client, message):
            return
        if len(message.text.split(maxsplit=1)) < 2:
            await message.reply_text("Usage: `/setsuffix [_text]`")
            return
        txt = message.text.split(maxsplit=1)[1]
        set_suffix(message.from_user.id, txt)
        await message.reply_text(f"✅ Suffix set: `{txt}`")
        try:
            await message.react(pick_reaction("settings"))
        except Exception:
            pass

    @app.on_message(filters.command("rename") & filters.private)
    async def rename_cmd(app_: Client, message: Message):
        if is_banned(message.from_user.id):
            return
        if not await ensure_forcesub(app_, message):
            return

        if not message.reply_to_message or not (
            message.reply_to_message.document or message.reply_to_message.video
        ):
            await message.reply_text(
                "Kisi **document/video par reply** karke `/rename new_name.ext` bhejo."
            )
            return

        if len(message.text.split(maxsplit=1)) < 2:
            await message.reply_text("Usage: `/rename new_name.ext`", quote=True)
            return

        new_name = message.text.split(maxsplit=1)[1].strip()
        if not new_name:
            await message.reply_text("Valid new_name.ext do.", quote=True)
            return

        status = await message.reply_text("⬇️ File download ho rahi hai rename ke liye...")
        dl_path = await app_.download_media(message.reply_to_message)

        import os
        new_path = new_name
        os.replace(dl_path, new_path)

        progress_msg = await message.reply_text("📤 Re-upload start ho raha hai...")
        await upload_with_thumb_and_progress(
            app_, message, new_path, message.from_user.id, progress_msg
        )
        await status.delete()
        try:
            await message.react(pick_reaction("rename"))
        except Exception:
            pass
