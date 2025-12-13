import os
import subprocess
from typing import Optional, List


# -------------------------------------------------
#   HELPERS
# -------------------------------------------------

def _run(cmd: list) -> bool:
    try:
        subprocess.run(cmd, check=True)
        return True
    except Exception as e:
        print("[media_tools] ffmpeg error:", e)
        return False


# -------------------------------------------------
#   DURATION
# -------------------------------------------------

def get_media_duration(path: str) -> Optional[int]:
    if not os.path.exists(path):
        return None
    try:
        out = subprocess.check_output(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ]
        ).decode().strip()

        dur = int(float(out))
        return dur if dur > 0 else None
    except Exception as e:
        print("[media_tools] duration error:", e)
        return None


# -------------------------------------------------
#   THUMBNAIL
# -------------------------------------------------

def generate_thumbnail_frame(
    path: str,
    out_path: str,
    at_second: int = 3
) -> Optional[str]:

    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        cmd_fast = [
            "ffmpeg", "-y",
            "-ss", str(at_second),
            "-i", path,
            "-frames:v", "1",
            "-q:v", "2",
            out_path,
        ]

        if _run(cmd_fast) and os.path.exists(out_path):
            return out_path

        # fallback seek
        cmd_safe = [
            "ffmpeg", "-y",
            "-i", path,
            "-ss", str(at_second),
            "-frames:v", "1",
            "-q:v", "2",
            out_path,
        ]

        if _run(cmd_safe) and os.path.exists(out_path):
            return out_path

    except Exception as e:
        print("[media_tools] thumbnail error:", e)

    return None


# -------------------------------------------------
#   SAMPLE CLIP (SMART)
# -------------------------------------------------

def generate_sample_clip(
    path: str,
    out_path: str,
    duration: int = 0,
    start_at: int = 0
) -> Optional[str]:

    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)

        total = get_media_duration(path)

        # AUTO SAMPLE LENGTH
        if not duration:
            if not total:
                duration = 15
            elif total < 60:
                duration = 10
            elif total < 5 * 60:
                duration = 20
            else:
                duration = 30

        if total and start_at + duration > total:
            start_at = max(0, total - duration - 1)

        # 1️⃣ TRY STREAM COPY (FAST)
        cmd_copy = [
            "ffmpeg", "-y",
            "-ss", str(start_at),
            "-i", path,
            "-t", str(duration),
            "-c", "copy",
            out_path,
        ]

        if _run(cmd_copy) and os.path.exists(out_path):
            return out_path

        # 2️⃣ SAFE RE-ENCODE (Telegram compatible)
        cmd_re = [
            "ffmpeg", "-y",
            "-ss", str(start_at),
            "-i", path,
            "-t", str(duration),
            "-map", "0:v:0",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-profile:v", "main",
            "-preset", "veryfast",
            "-movflags", "+faststart",
            "-c:a", "aac",
            out_path,
        ]

        if _run(cmd_re) and os.path.exists(out_path):
            return out_path

    except Exception as e:
        print("[media_tools] sample error:", e)

    return None


# -------------------------------------------------
#   FASTSTART
# -------------------------------------------------

def ensure_mp4_faststart(path: str) -> bool:
    try:
        base, _ = os.path.splitext(path)
        tmp = base + "_faststart.mp4"

        cmd = [
            "ffmpeg", "-y",
            "-i", path,
            "-c", "copy",
            "-movflags", "+faststart",
            tmp,
        ]

        if _run(cmd) and os.path.exists(tmp):
            os.replace(tmp, path)
            return True

    except Exception as e:
        print("[media_tools] faststart error:", e)

    return False


# -------------------------------------------------
#   SCREENSHOTS
# -------------------------------------------------

def generate_screenshots(
    path: str,
    out_dir: str,
    count: int = 3
) -> List[str]:

    screenshots: List[str] = []
    dur = get_media_duration(path)

    if not dur:
        print("[media_tools] screenshots skipped (no duration)")
        return screenshots

    os.makedirs(out_dir, exist_ok=True)

    step = max(1, dur // (count + 1))

    for i in range(1, count + 1):
        sec = i * step
        outp = os.path.join(out_dir, f"screenshot_{i}.jpg")

        thumb = generate_thumbnail_frame(path, outp, at_second=sec)
        if thumb:
            screenshots.append(thumb)

    return screenshots
