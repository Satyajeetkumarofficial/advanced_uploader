# utils/downloader.py
import os
import mimetypes
import time
from urllib.parse import urlparse

import aiohttp
import requests
from yt_dlp import YoutubeDL

from utils.progress import human_readable

# ==========================================
#   BASIC HELPERS
# ==========================================

VIDEO_EXTS = [
    ".mp4", ".mkv", ".mov", ".webm", ".flv", ".avi", ".m4v",
    ".3gp", ".ts", ".m2ts", ".ogv"
]

AUDIO_EXTS = [
    ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav",
]

DOC_LIKE_EXTS = [
    ".pdf", ".zip", ".rar", ".7z", ".apk", ".exe", ".txt", ".csv", ".xls", ".xlsx",
    ".doc", ".docx", ".ppt", ".pptx", ".iso", ".gz", ".tar", ".xz",
]

HTML_EXTS = [".html", ".htm", ".php", ".asp", ".aspx", ".jsp"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

COOKIES_FILE = os.getenv("COOKIES_FILE", "cookies.txt")
PROXY_URL = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY") or None  # optional proxy


# ----------------------- EXT HELPERS ----------------------- #

def is_video_ext(filename: str) -> bool:
    """
    Simple extension check to detect video-like files.
    """
    name = (filename or "").lower()
    for ext in VIDEO_EXTS + [".m3u8"]:
        if name.endswith(ext):
            return True
    return False


def is_audio_ext(filename: str) -> bool:
    name = (filename or "").lower()
    for ext in AUDIO_EXTS:
        if name.endswith(ext):
            return True
    return False


def is_html_like(filename: str) -> bool:
    name = (filename or "").lower()
    for ext in HTML_EXTS:
        if name.endswith(ext):
            return True
    return False


def _guess_extension_from_type(content_type: str | None) -> str | None:
    if not content_type:
        return None
    ext = mimetypes.guess_extension(content_type.split(";")[0].strip())
    if not ext:
        return None
    return ext


# ----------------------- URL NORMALIZE ----------------------- #

def normalize_url(url: str) -> str:
    """
    Try to resolve some redirecting/share URLs to their final location.
    """
    try:
        lower = url.lower()
        if "facebook.com/share/" in lower or "fb.watch" in lower:
            resp = requests.get(
                url,
                allow_redirects=True,
                timeout=15,
                headers={"User-Agent": USER_AGENT},
                proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None,
            )
            return resp.url or url
    except Exception:
        pass
    return url


# ----------------------- HEAD INFO ----------------------- #

def head_info(url: str) -> tuple[int, str | None, str | None]:
    """
    Do a HEAD request to get Content-Length, Content-Type, filename (if possible).
    Returns: (size_in_bytes_or_0, content_type_or_None, suggested_filename_or_None)
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
            proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None,
        )
        if resp.status_code >= 400:
            # some servers don't allow HEAD; try GET
            resp = requests.get(
                url,
                stream=True,
                timeout=10,
                headers={"User-Agent": USER_AGENT},
                proxies={"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None,
            )
        ctype = resp.headers.get("Content-Type")

        cl = resp.headers.get("Content-Length")
        if cl and cl.isdigit():
            size = int(cl)

        cd = resp.headers.get("Content-Disposition")
        if cd and "filename=" in cd:
            part = cd.split("filename=")[-1].strip().strip('"')
            filename = part
        else:
            parsed = urlparse(resp.url)
            base = os.path.basename(parsed.path)
            if base:
                filename = base

        if not filename and ctype:
            ext = _guess_extension_from_type(ctype)
            if ext:
                filename = "file" + ext

    except Exception:
        pass

    return size, ctype, filename


# ==========================================
#   YT-DLP POWERED DOWNLOADER
# ==========================================

def _build_ydl_opts(
    url: str,
    outtmpl: str,
    download: bool,
    fmt: str | None = None,
) -> dict:
    """
    Common yt-dlp options builder.
    """
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    ydl_opts: dict = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "merge_output_format": "mp4",
        "concurrent_fragment_downloads": 4,
        "retries": 5,
        "http_headers": {
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    if PROXY_URL:
        ydl_opts["proxy"] = PROXY_URL

    if not download:
        ydl_opts["skip_download"] = True

    # base format logic
    if fmt:
        ydl_opts["format"] = fmt
    else:
        # Prefer combined audio+video, fallback to mp4/best
        ydl_opts["format"] = "bv*+ba/bestvideo+bestaudio/best[ext=mp4]/best"

    # ensure postprocessor for faststart
    ydl_opts.setdefault("postprocessor_args", ["-movflags", "+faststart"])

    # site specific tweaks
    if any(h in host for h in ["youtube.com", "youtu.be", "youtubekids.com", "m.youtube.com"]):
        if os.path.exists(COOKIES_FILE):
            ydl_opts["cookiefile"] = COOKIES_FILE
        ydl_opts.setdefault("compat_opts", [])
        ydl_opts["compat_opts"] = list(set(ydl_opts["compat_opts"] + ["jsinterp", "retry_forever"]))

    if "facebook.com" in host or "fb.watch" in url:
        ydl_opts.update(
            {
                "nocheckcertificate": True,
                "extract_flat": False,
                "compat_opts": list(set((ydl_opts.get("compat_opts") or []) + ["jsinterp", "retry_forever"])),
                "extractor_args": {
                    "facebook": {
                        "hd": True,
                        "dcr": True,
                        "use_hls": True,
                        "skip_hls": False,
                    }
                },
                "geo_bypass": True,
                "geo_bypass_country": "US",
            }
        )

    if "instagram.com" in host:
        ydl_opts.setdefault("extractor_args", {})
        ydl_opts["extractor_args"]["instagram"] = {"max_requests": 5, "prefer_https": True}

    if "tiktok.com" in host:
        ydl_opts.setdefault("extractor_args", {})
        ydl_opts["extractor_args"]["tiktok"] = {"download_addr": True}

    if "twitter.com" in host or "x.com" in host:
        ydl_opts.setdefault("extractor_args", {})
        ydl_opts["extractor_args"]["twitter"] = {"legacy_api": "true"}

    if "reddit.com" in host:
        ydl_opts.setdefault("extractor_args", {})
        ydl_opts["extractor_args"]["reddit"] = {"video": True, "audio": True}

    if any(x in host for x in ["vimeo.com", "dailymotion.com", "ok.ru", "rumble.com", "streamable.com"]):
        ydl_opts.setdefault("compat_opts", [])
        ydl_opts["compat_opts"] = list(set(ydl_opts["compat_opts"] + ["jsinterp"]))

    if "drive.google.com" in host:
        ydl_opts.setdefault("extractor_args", {})
        ydl_opts["extractor_args"]["gdrive"] = {"skip_drive_warning": True}

    return ydl_opts


def is_ytdlp_site(url: str) -> bool:
    """
    Let yt-dlp try for most URLs.
    """
    return True


# ==========================================
#   LIST FORMATS
# ==========================================

def get_formats(url: str) -> tuple[list[dict], dict]:
    """
    Use yt-dlp to fetch available formats for a URL.
    Returns (formats_list, full_info_dict)
    """
    url = normalize_url(url)
    ydl_opts = _build_ydl_opts(url, outtmpl="NA", download=False)
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        if "facebook.com" in host or "fb.watch" in url:
            fallback_opts = ydl_opts.copy()
            fallback_opts["force_generic_extractor"] = True
            fallback_opts["extract_flat"] = False
            fallback_opts.pop("extractor_args", None)
            with YoutubeDL(fallback_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        else:
            raise e

    formats = info.get("formats", []) or []
    simple_formats = []

    for f in formats:
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        ext = (f.get("ext") or "").lower()

        if ext in ["gif", "jpg", "jpeg", "png", "webp"]:
            continue

        if vcodec == "none" or acodec == "none":
            continue

        fmt = {
            "format_id": f.get("format_id"),
            "ext": ext or "mp4",
            "height": f.get("height"),
            "filesize": f.get("filesize") or f.get("filesize_approx") or 0,
        }

        if fmt["format_id"]:
            simple_formats.append(fmt)

    if not simple_formats:
        for f in formats:
            vcodec = f.get("vcodec")
            ext = (f.get("ext") or "").lower()
            if ext in ["gif", "jpg", "jpeg", "png", "webp"]:
                continue
            if vcodec == "none":
                continue
            fmt = {
                "format_id": f.get("format_id"),
                "ext": ext or "mp4",
                "height": f.get("height"),
                "filesize": f.get("filesize") or f.get("filesize_approx") or 0,
            }
            if fmt["format_id"]:
                simple_formats.append(fmt)

    simple_formats.sort(key=lambda x: (x.get("height") or 0), reverse=True)

    return simple_formats, info


# ==========================================
#   DOWNLOAD WITH YT-DLP
# ==========================================

def download_with_ytdlp(url: str, fmt_id: str | None, tmp_name: str) -> str | None:
    """
    Download selected format using yt-dlp.
    If fmt_id is None => use bestvideo+bestaudio/best
    Returns final downloaded file path or None on failure.
    """
    url = normalize_url(url)
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    ydl_opts = _build_ydl_opts(url, outtmpl=tmp_name, download=True, fmt=fmt_id)

    safe_tmpl = tmp_name or "temp_ytdlp_video"
    ydl_opts["outtmpl"] = safe_tmpl + ".%(ext)s"
    ydl_opts["restrictfilenames"] = True
    ydl_opts["trim_file_name"] = 80

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            real_path = None
            try:
                real_path = ydl.prepare_filename(info)
            except Exception:
                # fallback guess
                real_path = None

            # If file exists, try faststart and return
            if real_path and os.path.exists(real_path):
                try:
                    from utils.media_tools import ensure_mp4_faststart
                    _ens = ensure_mp4_faststart(real_path)
                    if _ens:
                        print(f"[downloader] faststart remux applied for {real_path}")
                except Exception:
                    pass
                return real_path

    except Exception as e:
        # If Facebook-like, try generic extractor fallback
        if "facebook.com" in host or "fb.watch" in url:
            try:
                fallback_opts = ydl_opts.copy()
                fallback_opts["force_generic_extractor"] = True
                fallback_opts["extract_flat"] = False
                fallback_opts.pop("extractor_args", None)
                with YoutubeDL(fallback_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    try:
                        real_path = ydl.prepare_filename(info)
                        if real_path and os.path.exists(real_path):
                            try:
                                from utils.media_tools import ensure_mp4_faststart
                                _ens = ensure_mp4_faststart(real_path)
                                if _ens:
                                    print(f"[downloader] faststart remux applied for {real_path}")
                            except Exception:
                                pass
                            return real_path
                    except Exception:
                        pass
            except Exception:
                pass
        # otherwise re-raise
        print(f"[downloader] yt-dlp error: {e}")
        return None

    # If we reach here yt-dlp didn't return a file
    return None


# ==========================================
#   DIRECT DOWNLOAD WITH PROGRESS
# ==========================================

async def download_direct_with_progress(url: str, filename: str, progress_msg):
    """
    Direct HTTP(S) download using aiohttp with telegram message progress.
    Returns (local_path, total_downloaded_bytes)
    """
    url = normalize_url(url)

    filename = filename or "file_from_url"
    local_path = os.path.join(".", filename)

    total_size = 0
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
                total_size = int(cl)

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
                        text = _format_progress_text(
                            "⬇️ Downloading",
                            downloaded,
                            total_size,
                            start_time,
                        )
                        try:
                            await progress_msg.edit_text(text)
                        except Exception:
                            pass

    try:
        text = _format_progress_text(
            "✅ Download complete",
            downloaded,
            total_size,
            start_time,
        )
        await progress_msg.edit_text(text)
    except Exception:
        pass

    return local_path, downloaded


def _format_progress_text(prefix: str, downloaded: int, total: int, start_time: float) -> str:
    """
    Human-readable progress text for Telegram message.
    """
    elapsed = max(time.time() - start_time, 1e-3)
    speed = downloaded / elapsed

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
