import os
import re
import time
import math
import mimetypes
import asyncio
from urllib.parse import urlparse, unquote

import aiohttp
import requests
from yt_dlp import YoutubeDL

from utils.progress import human_readable


# ==========================================
#   GLOBAL CONSTANTS
# ==========================================

VIDEO_EXTS = [
    ".mp4", ".mkv", ".mov", ".webm", ".flv", ".avi", ".m4v", ".3gp",
    ".ts", ".m2ts", ".ogv", ".mpeg", ".mpg"
]

AUDIO_EXTS = [
    ".mp3", ".aac", ".m4a", ".ogg", ".opus", ".flac", ".wav"
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
#   EXTENSION + FILENAME HELPERS
# ==========================================

def is_video_ext(filename: str) -> bool:
    if not filename:
        return False
    name = filename.lower()
    for ext in VIDEO_EXTS + [".m3u8"]:
        if name.endswith(ext):
            return True
    return False


def guess_ext_from_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return mimetypes.guess_extension(content_type.split(";")[0].strip()) or None


def sanitize_filename(name: str, max_len: int = SAFE_FILENAME_LEN) -> str:
    if not name:
        return "video"
    name = unquote(name)
    name = re.sub(r"[\\/:*?\"<>|]", "", name)
    if len(name) > max_len:
        name = name[:max_len]
    return name.strip() or "video"


# ==========================================
#   URL NORMALIZATION
# ==========================================

def normalize_url(url: str) -> str:
    """
    Facebook share links, redirect URLs, shorteners etc → resolve to real URL.
    """
    try:
        low = url.lower()

        if any(x in low for x in [
            "facebook.com/share/",
            "fb.watch"
        ]):
            resp = requests.get(
                url,
                allow_redirects=True,
                timeout=10,
                headers={"User-Agent": USER_AGENT},
                proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None,
            )
            return resp.url or url

        if "vt.tiktok.com" in low or "vm.tiktok.com" in low:
            resp = requests.get(
                url,
                allow_redirects=True,
                timeout=10,
                headers={"User-Agent": USER_AGENT},
            )
            return resp.url or url

        if "x.com/" in low:
            return url.replace("x.com", "twitter.com")

    except Exception:
        return url

    return url


# ==========================================
#   BASIC HEAD REQUEST (size/type)
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
            filename = f"file{ext}" if ext else None

    except Exception:
        pass

    return size, ctype, filename


# ==========================================
#   YT-DLP OPTION BUILDER
# ==========================================

def _build_ydl_opts(url: str, outtmpl: str, download=True, fmt=None):
    parsed = urlparse(url)
    host = parsed.netloc.lower()

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

    ydl_opts["format"] = fmt if fmt else (
        "bv*+ba/bestvideo+bestaudio/best"
    )

    # Cookies (for YT)
    if "youtube.com" in host or "youtu.be" in host:
        if os.path.exists(COOKIES_FILE):
            ydl_opts["cookiefile"] = COOKIES_FILE
        ydl_opts.setdefault("compat_opts", [])
        ydl_opts["compat_opts"] += ["jsinterp", "retry_forever"]

    # FACEBOOK FIXES
    if "facebook.com" in host or "fb.watch" in url:
        ydl_opts.update({
            "compat_opts": ["facebook_mess", "jsinterp"],
            "extract_flat": False,
            "extractor_args": {
                "facebook": {
                    "hd": True,
                    "dcr": True,
                    "use_hls": True,
                    "skip_hls": False,
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

    # Drive
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
    host = parsed.netloc.lower()

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

def sanitize_filename(name: str):
    """
    Remove dangerous characters, trim long titles, keep file safe.
    """
    bad = r'<>:"/\|?*'
    for b in bad:
        name = name.replace(b, "")
    name = name.strip().replace("\n", " ").replace("\r", " ")

    if len(name) > SAFE_FILENAME_LEN:
        name = name[:SAFE_FILENAME_LEN]

    return name


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
    When yt-dlp cannot download → fallback direct HTTP downloader.
    Supports:
      ✔ large files
      ✔ auto ETA
      ✔ speed display
      ✔ every 3 sec update
    """
    url = normalize_url(url)
    filename = sanitize_filename(filename or "file")

    local_path = os.path.join(".", filename)

    total = 0
    done = 0
    last_update = 0
    start = time.time()

    timeout = aiohttp.ClientTimeout(total=0, sock_connect=15, sock_read=0)

    headers = {"User-Agent": USER_AGENT}

    connector_kwargs = {}
    if PROXY_URL:
        connector_kwargs["ssl"] = False

    async with aiohttp.ClientSession(
        timeout=timeout,
        headers=headers,
        **connector_kwargs
    ) as session:

        req = {}
        if PROXY_URL:
            req["proxy"] = PROXY_URL

        async with session.get(url, **req) as resp:
            resp.raise_for_status()

            cl = resp.headers.get("Content-Length")
            if cl and cl.isdigit():
                total = int(cl)

            os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

            with open(local_path, "wb") as f:
                async for chunk in resp.content.iter_chunked(1024 * 128):
                    if not chunk:
                        continue

                    f.write(chunk)
                    done += len(chunk)

                    now = time.time()
                    if now - last_update >= 3:
                        last_update = now
                        try:
                            await progress_msg.edit_text(
                                format_progress("⬇️ Downloading", done, total, start)
                            )
                        except:
                            pass

    try:
        await progress_msg.edit_text(
            format_progress("✅ Download Complete", done, total, start)
        )
    except:
        pass

    return local_path, done


# ==========================================
#   PROGRESS BAR TEXT
# ==========================================

def format_progress(prefix: str, done: int, total: int, start: float):
    elapsed = max(time.time() - start, 0.001)
    speed = done / elapsed

    if total > 0:
        percent = done * 100 / total
        filled = int(percent // 5)
        bar = "█" * filled + "─" * (20 - filled)
        total_str = human_readable(total)
    else:
        percent = 0
        bar = "───────────────"
        total_str = "Unknown"

    done_str = human_readable(done)
    speed_str = human_readable(int(speed)) + "/s"

    if total > 0:
        remaining = (total - done) / speed if speed > 0 else 0
        mm, ss = divmod(int(remaining), 60)
        eta = f"{mm}m {ss}s"
    else:
        eta = "Calculating..."

    return (
        f"{prefix}\n"
        f"[{bar}] {percent:.1f}%\n"
        f"Downloaded: {done_str} / {total_str}\n"
        f"Speed: {speed_str}\n"
        f"ETA: {eta}"
    )


# ==========================================
#   UNIVERSAL VIDEO DETECTION (HTML SAFE)
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
        if "video" in low or "audio" in low or "application/octet-stream" in low:
            return True

    # avoid html pages
    parsed = urlparse(url).path.lower()
    if parsed.endswith(".html") or parsed.endswith(".htm") or parsed.endswith(".php"):
        return False

    return False


# ==========================================
#   UNIVERSAL FALLBACK DOWNLOAD
# ==========================================

async def ultra_fallback_download(url: str, progress_msg):
    """
    If yt-dlp + direct both fail:
    Try:
      ✔ m3u8 sniffing
      ✔ MP4 direct link extraction
      ✔ simple redirect-tracing
    """
    try:
        resp = requests.get(
            url, timeout=10,
            allow_redirects=True,
            headers={"User-Agent": USER_AGENT},
            proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
        )

        # M3U8 detection
        if ".m3u8" in resp.text:
            return _download_m3u8_inline(url, progress_msg)

        # Find any mp4 direct link in HTML
        if ".mp4" in resp.text:
            mp4_link = _extract_first_mp4(resp.text, url)
            if mp4_link:
                return await download_direct_with_progress(
                    mp4_link,
                    "video.mp4",
                    progress_msg
                )

    except Exception:
        pass

    raise Exception("❌ Ultra fallback failed.")


def _extract_first_mp4(text: str, base_url: str):
    """
    Extract first .mp4 URL from HTML.
    """
    try:
        import re
        matches = re.findall(r'https?://[^"\' ]+\.mp4', text)
        if matches:
            return matches[0]

        # relative mp4: /videos/x.mp4
        rel = re.findall(r'\/[^"\' ]+\.mp4', text)
        if rel:
            from urllib.parse import urljoin
            return urljoin(base_url, rel[0])
    except:
        return None


def _download_m3u8_inline(url: str, progress_msg):
    """
    Internal simple M3U8 downloader.
    (yt-dlp usually handles it, but fallback just in case)
    """
    import subprocess
    out = f"m3u8_{int(time.time())}.mp4"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", url,
        "-c", "copy",
        out,
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out, os.path.getsize(out)
    except:
        return None


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
      1️⃣ HEAD check → video? use direct download
      2️⃣ yt-dlp try
      3️⃣ fallback direct
      4️⃣ ultra fallback (HTML → mp4 / m3u8 detect)
    """
    url = normalize_url(url)

    # ---------- STEP 1 → HEAD CHECK ----------
    size, ctype, filename = head_info(url)

    if force_direct:
        # forced direct mode
        return await download_direct_with_progress(url, filename or "file", progress_msg)

    if is_probably_video(url, ctype, filename):
        try:
            return await download_direct_with_progress(url, filename or "file", progress_msg)
        except:
            pass

    # ---------- STEP 2 → YT-DLP TRY ----------
    tmp = f"temp_{int(time.time())}"
    try:
        local = download_with_ytdlp(url, fmt_id, tmp)
        return local, os.path.getsize(local)
    except Exception:
        pass

    # ---------- STEP 3 → DIRECT FALLBACK ----------
    try:
        return await download_direct_with_progress(url, filename or "file", progress_msg)
    except:
        pass

    # ---------- STEP 4 → ULTRA-ULTIMATE FALLBACK ----------
    try:
        return await ultra_fallback_download(url, progress_msg)
    except:
        pass

    raise Exception("❌ All download methods failed.")


# ==========================================
#   EXTRA HELPERS (OPTIONAL BUT USEFUL)
# ==========================================

def is_audio_ext(filename: str) -> bool:
    if not filename:
        return False
    name = filename.lower()
    for ext in AUDIO_EXTS:
        if name.endswith(ext):
            return True
    return False


def choose_filename_from_info(info: dict, default: str = "video") -> str:
    """
    yt-dlp info dict se best filename choose karta hai.
    """
    name = info.get("title") or default
    ext = info.get("ext") or "mp4"
    base = sanitize_filename(name)
    return f"{base}.{ext}"


# ==========================================
#   PUBLIC EXPORTED API
# ==========================================
#   Ye functions tumhare bot ke dusre modules use kar sakte hain:
#
#   - is_video_ext(filename)
#   - head_info(url)
#   - get_formats(url)
#   - download_with_ytdlp(url, fmt_id, tmp_name)
#   - download_direct_with_progress(url, filename, progress_msg)
#   - ultra_download_manager(url, fmt_id, progress_msg, force_direct=False)
#   - format_progress(prefix, done, total, start)


async def smart_download(
    url: str,
    fmt_id: str | None,
    progress_msg,
    force_direct: bool = False
):
    """
    Simple wrapper jo tum handlers me use kar sakte ho:

        local_path, size = await smart_download(url, fmt_id, msg)

    Ye internally ultra_download_manager ko call karta hai.
    """
    return await ultra_download_manager(url, fmt_id, progress_msg, force_direct=force_direct)
