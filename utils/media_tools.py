import os
import subprocess
from typing import List, Optional


def get_media_duration(path: str) -> Optional[int]:
    """
    ffprobe se duration (seconds) nikalta hai.
    """
    try:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode().strip()
        if not out:
            return None
        val = float(out)
        if val <= 0:
            return None
        return int(val + 0.5)
    except Exception:
        return None


def generate_screenshots(path: str, out_dir: str, count: int = 6) -> List[str]:
    """
    Album ke liye multiple screenshots (default 6).
    """
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        return []

    duration = get_media_duration(path)
    if not duration or duration <= 0:
        # Fallback timings
        times = [5, 15, 30, 45, 60, 75][:count]
    else:
        step = max(duration // (count + 1), 1)
        times = [step * (i + 1) for i in range(count)]

    shots = []
    for idx, t in enumerate(times, start=1):
        out_path = os.path.join(out_dir, f"shot_{idx}.jpg")
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(t),
            "-i",
            path,
            "-frames:v",
            "1",
            "-vf",
            "scale=320:-1:force_original_aspect_ratio=decrease",
            "-q:v",
            "5",
            out_path,
        ]
        try:
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            if os.path.exists(out_path):
                shots.append(out_path)
        except Exception:
            continue
    return shots


def generate_thumbnail_frame(path: str, out_path: str) -> Optional[str]:
    """
    Ek beech ka frame thumbnail ke liye (video ka 'sense' dikhe).
    """
    dur = get_media_duration(path)
    if dur and dur > 4:
        t = dur // 2  # middle of video
    else:
        t = 2

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(t),
        "-i",
        path,
        "-frames:v",
        "1",
        "-vf",
        "scale=320:-1:force_original_aspect_ratio=decrease",
        "-q:v",
        "4",
        out_path,
    ]
    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        if os.path.exists(out_path):
            return out_path
    except Exception:
        pass
    return None
