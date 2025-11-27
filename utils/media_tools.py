import os
import subprocess
from typing import List


def generate_screenshots(input_path: str, out_dir: str, count: int = 3) -> List[str]:
    if not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    times = [5, 15, 25][:count]
    outputs = []

    for i, t in enumerate(times, start=1):
        out_path = os.path.join(out_dir, f"shot_{i}.jpg")
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(t),
            "-i",
            input_path,
            "-frames:v",
            "1",
            "-q:v",
            "3",
            out_path,
        ]
        try:
            subprocess.run(
                cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            if os.path.exists(out_path):
                outputs.append(out_path)
        except Exception:
            continue

    return outputs


def generate_sample_clip(input_path: str, out_path: str, duration: int = 15) -> str | None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-t",
        str(duration),
        "-c",
        "copy",
        out_path,
    ]
    try:
        subprocess.run(
            cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if os.path.exists(out_path):
            return out_path
    except Exception:
        return None
    return None
