import os
import subprocess
from typing import Optional, List

def get_media_duration(path: str) -> Optional[int]:
    """
    Return media duration in seconds (int) using ffprobe.
    Returns None on error.
    """
    if not os.path.exists(path):
        return None
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        out = out.decode().strip()
        if not out:
            return None
        duration = int(float(out))
        return duration
    except Exception:
        return None


def generate_thumbnail_frame(path: str, out_path: str, at_second: int = 3) -> Optional[str]:
    """
    Extract a frame at `at_second` seconds to use as thumbnail.
    Returns output path on success else None.
    """
    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        # Try fast seek before input
        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(at_second),
            "-i", path,
            "-frames:v", "1",
            "-q:v", "2",
            out_path,
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(out_path):
                return out_path
        except Exception:
            # fallback: more compatible seek after input
            cmd2 = [
                "ffmpeg",
                "-y",
                "-i", path,
                "-ss", str(at_second),
                "-frames:v", "1",
                "-q:v", "2",
                out_path,
            ]
            try:
                subprocess.run(cmd2, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                if os.path.exists(out_path):
                    return out_path
            except Exception:
                pass
    except Exception:
        pass
    return None


def generate_sample_clip(path: str, out_path: str, duration: int = 10, start_at: int = 0) -> Optional[str]:
    """
    Generate a short sample clip from `path`.
    `duration` in seconds. `start_at` is start time in seconds.
    Tries fast streamcopy first, falls back to re-encode if that fails.
    Returns out_path on success else None.
    """
    try:
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        # Try stream copy (fast)
        cmd_copy = [
            "ffmpeg",
            "-y",
            "-ss", str(start_at),
            "-i", path,
            "-t", str(duration),
            "-c", "copy",
            out_path,
        ]
        try:
            subprocess.run(cmd_copy, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(out_path):
                return out_path
        except Exception:
            # fallback to re-encode (more compatible)
            cmd_reencode = [
                "ffmpeg",
                "-y",
                "-ss", str(start_at),
                "-i", path,
                "-t", str(duration),
                "-c:v", "libx264",
                "-c:a", "aac",
                "-strict", "-2",
                out_path,
            ]
            try:
                subprocess.run(cmd_reencode, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                if os.path.exists(out_path):
                    return out_path
            except Exception:
                pass
    except Exception:
        pass
    return None


def ensure_mp4_faststart(path: str) -> bool:
    """
    Remux file to ensure moov atom at start for progressive streaming.
    Overwrites original file on success.
    """
    try:
        base, ext = os.path.splitext(path)
        tmp = base + "_faststart.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-i", path,
            "-c", "copy",
            "-movflags", "+faststart",
            tmp,
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(tmp):
            os.replace(tmp, path)
            return True
    except Exception:
        pass
    return False


def generate_screenshots(path: str, out_dir: str, count: int = 3) -> List[str]:
    """
    Generate `count` evenly spaced screenshots. Returns list of file paths (may be empty).
    """
    screenshots = []
    dur = get_media_duration(path)
    if not dur:
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
