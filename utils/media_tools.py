import os
import math
import subprocess
from typing import List, Optional


def get_media_duration(path: str) -> Optional[int]:
    """
    ffprobe se duration (seconds) nikalta hai.
    Agar nahi mila to None return karega.
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


def generate_screenshots(path: str, out_dir: str, count: int = 3) -> List[str]:
    """
    Video se 1 ya zyada screenshots generate karega.
    ffmpeg + ffprobe use karta hai.
    """
    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception:
        return []

    duration = get_media_duration(path)
    if not duration or duration <= 0:
        # fallback timings (5, 15, 30 sec)
        times = [5, 15, 30][:count]
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
            "-q:v",
            "2",
            out_path,
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(out_path):
                shots.append(out_path)
        except Exception:
            continue
    return shots


def generate_sample_clip(path: str, out_path: str, duration_sec: int = 15) -> Optional[str]:
    """
    Video ke starting se `duration_sec` seconds ka sample clip banata hai.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        "0",
        "-i",
        path,
        "-t",
        str(duration_sec),
        "-c",
        "copy",
        out_path,
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if os.path.exists(out_path):
            return out_path
    except Exception:
        pass
    return None
