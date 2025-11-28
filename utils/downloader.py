import os
import re
import time
import mimetypes
from urllib.parse import urlparse, unquote

import aiohttp
import requests
from yt_dlp import YoutubeDL

from utils.progress import human_readable


# ==========================================
#   GLOBAL CONSTANTS
# ==========================================

VIDEO_EXTS = [
    ".mp4", ".mkv", ".mov", ".webm", ".flv", ".avi", ".m4v",
    ".3gp", ".ts", ".m2ts", ".ogv", ".mpeg", ".mpg"
]

AUDIO_EXTS = [
    ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")

PROXY_URL = (
    os.getenv("HTTP_PROXY")
    or os.getenv("HTTPS_PROXY")
    or None
)

SAFE_FILENAME_LEN = 80


# ==========================================
#   BASIC HELPERS
# ==========================================

def is_video_ext(filename: str) -> bool:
    """Detect if file extension looks like a video / stream."""
    if not filename:
        return False
    name = filename.lower()
    for ext in VIDEO_EXTS + [".m3u8"]:
        if name.endswith(ext):
            return True
    return False


def is_audio_ext(filename: str) -> bool:
    if not filename:
        return False
    name = filename.lower()
    for ext in AUDIO_EXTS:
        if name.endswith(ext):
            return True
    return False


def guess_ext_from_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return mimetypes.guess_extension(
        content_type.split(";")[0].strip()
    ) or None


def sanitize_filename(name: str, max_len: int = SAFE_FILENAME_LEN) -> str:
    if not name:
        return "video"
    name = unquote(name)
    name = re.sub(r"[\\/:*?\"<>|]", "", name)
    name = name.replace("\n", " ").replace("\r", " ")
    name = name.strip()
    if len(name) > max_len:
        name = name[:max_len]
    return name or "video"


# ==========================================
#   URL NORMALIZATION
# ==========================================

def normalize_url(url: str) -> str:
    """
    Facebook share / fb.watch / shorteners ko real URL me convert karta hai.
    """
    try:
        low = url.lower()

        # facebook share / reel redirect
        if "facebook.com/share/" in low or "fb.watch" in low:
            resp = requests.get(
                url,
                allow_redirects=True,
                timeout=10,
                headers={"User-Agent": USER_AGENT},
                proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None,
            )
            return resp.url or url

        # tiktok short links
        if "vt.tiktok.com" in low or "vm.tiktok.com" in low:
            resp = requests.get(
                url,
                allow_redirects=True,
                timeout=10,
                headers={"User-Agent": USER_AGENT},
            )
            return resp.url or url

        # x.com → twitter.com
        if "x.com/" in low:
            return url.replace("x.com", "twitter.com")

    except Exception:
        return url

    return url


# ==========================================
#   HEAD REQUEST (SIZE / TYPE / FILENAME)
# ==========================================

def head_info(url: str):
    """
    Returns:
        size_bytes_or_0,
        content_type_or_None,
        filename_or_None
    """
    url = normalize_url(url)

    size = 0
    ctype = None
    filename = None

    try:
        resp = requests.head(
            url,
            allow_redirects=True,
            timeout=10,
            headers={"User-Agent": USER_AGENT},
            proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
        )

        if resp.status_code >= 400:
            resp = requests.get(
                url,
                stream=True,
                timeout=10,
                headers={"User-Agent": USER_AGENT},
                proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
            )

        ctype = resp.headers.get("Content-Type")

        cl = resp.headers.get("Content-Length")
        if cl and cl.isdigit():
            size = int(cl)

        cd = resp.headers.get("Content-Disposition")
        if cd and "filename=" in cd:
            filename = cd.split("filename=")[-1].replace('"', '').strip()
        else:
            parsed = urlparse(resp.url)
            base = os.path.basename(parsed.path)
            if base:
                filename = base

        if not filename and ctype:
            ext = guess_ext_from_type(ctype)
            if ext:
                filename = f"file{ext}"

    except Exception:
        pass

    return size, ctype, filename


# ==========================================
#   YT-DLP OPTION BUILDER
# ==========================================

def _build_ydl_opts(url: str, outtmpl: str, download=True, fmt=None):
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    ydl_opts = {
        "quiet": True,
        "noprogress": True,
        "no_warnings": True,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "restrictfilenames": True,
        "trim_file_name": SAFE_FILENAME_LEN,
        "retries": 5,
        "geo_bypass": True,
        "http_headers": {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    if not download:
        ydl_opts["skip_download"] = True

    if PROXY_URL:
        ydl_opts["proxy"] = PROXY_URL

    # Default best combo
    ydl_opts["format"] = fmt if fmt else "bv*+ba/bestvideo+bestaudio/best"

    # YOUTUBE
    if any(x in host for x in ["youtube.com", "youtu.be"]):
        if os.path.exists(COOKIES_FILE):
            ydl_opts["cookiefile"] = COOKIES_FILE
        ydl_opts.setdefault("compat_opts", [])
        ydl_opts["compat_opts"] += ["jsinterp", "retry_forever"]

    # FACEBOOK – FINAL PATCH (NO GIF, ALWAYS VIDEO+SOUND)
    if "facebook.com" in host or "fb.watch" in url:
        ydl_opts.update({
            "format": "bv*[vcodec!*=av01][vcodec!*=vp9]+ba/best",
            "merge_output_format": "mp4",
            "hls_prefer_native": True,
            "extract_flat": False,
            "nocheckcertificate": True,
            "geo_bypass": True,
            "geo_bypass_country": "US",
            "postprocessors": [
                {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}
            ],
            "compat_opts": [
                "jsinterp",
                "retry_forever",
                "facebook_subtitle_workaround",
                "facebook_mess",
            ],
            "extractor_args": {
                "facebook": {
                    "video": "true",
                    "audio": "true",
                    "dcr": "true",
                    "hd": "true",
                    "skip_hls": "false",
                    "use_hls": "true",
                    "recode": "mp4"
                }
            }
        })

    # INSTAGRAM
    if "instagram.com" in host:
        ydl_opts.setdefault("extractor_args", {})
        ydl_opts["extractor_args"]["instagram"] = {
            "max_requests": 5,
            "prefer_https": True,
        }

    # TIKTOK
    if "tiktok.com" in host:
        ydl_opts.setdefault("extractor_args", {})
        ydl_opts["extractor_args"]["tiktok"] = {"download_addr": True}

    # TWITTER / X
    if "twitter.com" in host:
        ydl_opts.setdefault("extractor_args", {})
        ydl_opts["extractor_args"]["twitter"] = {"legacy_api": "true"}

    # GOOGLE DRIVE
    if "drive.google.com" in host:
        ydl_opts.setdefault("extractor_args", {})
        ydl_opts["extractor_args"]["gdrive"] = {"skip_drive_warning": True}

    return ydl_opts


# ==========================================
#   FORMAT FETCHER
# ==========================================

def get_formats(url: str):
    url = normalize_url(url)
    opts = _build_ydl_opts(url, outtmpl="NA", download=False)

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception:
        if "facebook.com" in host or "fb.watch" in url:
            fallback = opts.copy()
            fallback["force_generic_extractor"] = True
            fallback["extract_flat"] = False
            fallback.pop("extractor_args", None)
            with YoutubeDL(fallback) as ydl:
                info = ydl.extract_info(url, download=False)
        else:
            raise

    formats = []
    for f in info.get("formats", []):

        if f.get("vcodec") == "none" and f.get("acodec") == "none":
            continue

        formats.append({
            "format_id": f.get("format_id"),
            "ext": f.get("ext", "mp4"),
            "height": f.get("height"),
            "filesize": f.get("filesize") or f.get("filesize_approx") or 0,
        })

    formats.sort(key=lambda x: (x["height"] or 0), reverse=True)

    return formats, info


# ==========================================
#   YT-DLP DOWNLOAD WRAPPER
# ==========================================

def download_with_ytdlp(url: str, fmt_id: str | None, tmp_name: str) -> str:
    """
    Ultra-MAX yt-dlp downloader
    => Always safe filename
    => Facebook fallback
    => Audio+Video merge
    """
    url = normalize_url(url)
    host = urlparse(url).netloc.lower()

    safe_base = sanitize_filename(tmp_name or "video_file")

    ydl_opts = _build_ydl_opts(
        url,
        outtmpl=safe_base + ".%(ext)s",
        download=True,
        fmt=fmt_id
    )

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            final_path = ydl.prepare_filename(info)
            return final_path

    except Exception as e:
        # FACEBOOK Fallback
        if "facebook.com" in host or "fb.watch" in url:
            fallback = ydl_opts.copy()
            fallback["force_generic_extractor"] = True
            fallback["extract_flat"] = False
            fallback.pop("extractor_args", None)

            with YoutubeDL(fallback) as ydl:
                info = ydl.extract_info(url, download=True)
                final_path = ydl.prepare_filename(info)
                return final_path

        raise e


# ==========================================
#   DIRECT HTTP DOWNLOAD WITH PROGRESS
# ==========================================

async def download_direct_with_progress(url: str, filename: str, progress_msg):
    """
    Direct HTTP(S) download using aiohttp with telegram message progress.
    Returns (local_path, total_downloaded_bytes)
    """
    url = normalize_url(url)

    filename = sanitize_filename(filename or "file")
    local_path = os.path.join(".", filename)

    total = 0
    downloaded = 0
    last_edit_time = 0
    start_time = time.time()

    timeout = aiohttp.ClientTimeout(total=0, sock_connect=20, sock_read=0)

    connector_kwargs = {}
    if PROXY_URL:
        connector_kwargs["ssl"] = False

    async with aiohttp.ClientSession(
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
        **connector_kwargs,
    ) as session:
        kwargs = {}
        if PROXY_URL:
            kwargs["proxy"] = PROXY_URL

        async with session.get(url, **kwargs) as resp:
            resp.raise_for_status()

            cl = resp.headers.get("Content-Length")
            if cl and cl.isdigit():
                total = int(cl)

            os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

            with open(local_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 64):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)

                    now = time.time()
                    if now - last_edit_time >= 3:
                        last_edit_time = now
                        text = format_progress(
                            "⬇️ Downloading",
                            downloaded,
                            total,
                            start_time,
                        )
                        try:
                            await progress_msg.edit_text(text)
                        except Exception:
                            pass

    # final progress update
    try:
        text = format_progress(
            "✅ Download complete",
            downloaded,
            total,
            start_time,
        )
        await progress_msg.edit_text(text)
    except Exception:
        pass

    return local_path, downloaded


# ==========================================
#   PROGRESS TEXT
# ==========================================

def format_progress(prefix: str, downloaded: int, total: int, start_time: float) -> str:
    """
    Human-readable progress text for Telegram message.
    """
    elapsed = max(time.time() - start_time, 1e-3)
    speed = downloaded / elapsed  # bytes/sec

    if total > 0:
        percent = downloaded * 100 / total
        bar_filled = int(percent // 5)
        bar = "█" * bar_filled + "─" * (20 - bar_filled)
        total_str = human_readable(total)
    else:
        percent = 0
        bar = "─" * 20
        total_str = "Unknown"

    downloaded_str = human_readable(downloaded)
    speed_str = human_readable(int(speed)) + "/s"

    if total > 0 and speed > 0:
        remaining = (total - downloaded) / speed
        mins, secs = divmod(int(remaining), 60)
        eta = f"{mins}m {secs}s"
    else:
        eta = "Calculating..."

    text = (
        f"{prefix}...\n"
        f"[{bar}] {percent:.1f}%\n"
        f"Downloaded: {downloaded_str} / {total_str}\n"
        f"Speed: {speed_str}\n"
        f"ETA: {eta}"
    )
    return text


# backward compatibility:
def _format_progress_text(prefix, downloaded, total, start_time):
    return format_progress(prefix, downloaded, total, start_time)


# ==========================================
#   VIDEO DETECTION FOR DIRECT MODE
# ==========================================

def is_probably_video(url: str, ctype: str | None, filename: str | None):
    """
    Decide if link is truly a video file:
      ✔ extension check
      ✔ content-type check
      ✔ avoid .html, .php, .asp etc.
    """
    if filename and is_video_ext(filename):
        return True

    if ctype:
        low = ctype.lower()
        if "video" in low or "audio" in low:
            return True

    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in [".html", ".htm", ".php", ".asp", ".aspx"]):
        return False

    return False


# ==========================================
#   ULTRA FALLBACK HELPERS
# ==========================================

def _extract_first_mp4(text: str, base_url: str):
    try:
        matches = re.findall(r'https?://[^"\' ]+\.mp4', text)
        if matches:
            return matches[0]

        rel = re.findall(r'\/[^"\' ]+\.mp4', text)
        if rel:
            from urllib.parse import urljoin
            return urljoin(base_url, rel[0])
    except Exception:
        return None


async def ultra_fallback_download(url: str, progress_msg):
    """
    If yt-dlp + direct both fail:
      ✔ Try to sniff m3u8/mp4 inside HTML
    """
    try:
        resp = requests.get(
            url,
            timeout=10,
            allow_redirects=True,
            headers={"User-Agent": USER_AGENT},
            proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None,
        )

        text = resp.text or ""

        if ".mp4" in text:
            mp4_link = _extract_first_mp4(text, resp.url)
            if mp4_link:
                return await download_direct_with_progress(
                    mp4_link,
                    "video.mp4",
                    progress_msg
                )

    except Exception:
        pass

    raise Exception("❌ Ultra fallback failed.")


# ==========================================
#   MASTER DOWNLOAD MANAGER
# ==========================================

async def ultra_download_manager(
    url: str,
    fmt_id: str | None,
    progress_msg,
    force_direct: bool = False
):
    """
    MASTER LOGIC:
      1️⃣ HEAD check → direct video? then direct download
      2️⃣ yt-dlp
      3️⃣ direct fallback
      4️⃣ ultra fallback (HTML sniff)
    """
    url = normalize_url(url)

    size, ctype, filename = head_info(url)

    if force_direct:
        return await download_direct_with_progress(url, filename or "file", progress_msg)

    if is_probably_video(url, ctype, filename):
        try:
            return await download_direct_with_progress(url, filename or "file", progress_msg)
        except Exception:
            pass

    # ytdlp
    tmp = f"temp_{int(time.time())}"
    try:
        local = download_with_ytdlp(url, fmt_id, tmp)
        return local, os.path.getsize(local)
    except Exception:
        pass

    # direct fallback
    try:
        return await download_direct_with_progress(url, filename or "file", progress_msg)
    except Exception:
        pass

    # ultra fallback
    try:
        return await ultra_fallback_download(url, progress_msg)
    except Exception:
        pass

    raise Exception("❌ All download methods failed.")


# ==========================================
#   SIMPLE PUBLIC WRAPPER
# ==========================================

async def smart_download(
    url: str,
    fmt_id: str | None,
    progress_msg,
    force_direct: bool = False
):
    """
    Wrapper jo handlers use kar sakte hain:
        local_path, size = await smart_download(url, fmt_id, msg)
    """
    return await ultra_download_manager(url, fmt_id, progress_msg, force_direct=force_direct)
