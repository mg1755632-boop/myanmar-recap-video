from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class VideoError(RuntimeError):
    pass


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise VideoError("FFmpeg is not installed or is not available on PATH.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "FFmpeg failed").strip()[-1200:]
        raise VideoError(detail) from exc


def get_media_info(video_path: str | Path) -> dict:
    result = _run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(video_path)])
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video:
        raise VideoError("The uploaded file does not contain a video stream.")
    return {
        "duration": float(data.get("format", {}).get("duration") or 0),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def extract_audio(video_path: str | Path, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(["ffmpeg", "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(output)])
    return output


def _escape_filter_path(path: str | Path) -> str:
    return str(Path(path).resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def _font_file() -> str | None:
    if not shutil.which("fc-match"):
        return None
    result = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans Myanmar"], capture_output=True, text=True)
    path = result.stdout.strip()
    return path if path and Path(path).exists() else None


def export_final_video(
    video_path: str | Path,
    voice_path: str | Path,
    srt_path: str | Path,
    output_path: str | Path,
    *,
    burn_subtitles: bool = True,
    blur_video: bool = False,
    blur_strength: int = 2,
    logo_text: str = "",
    logo_size: int = 28,
    logo_opacity: float = 0.18,
    logo_period: int = 24,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    filters: list[str] = []
    if blur_video:
        filters.append(f"boxblur=luma_radius={max(1, int(blur_strength))}:luma_power=1")
    if burn_subtitles:
        filters.append(f"subtitles='{_escape_filter_path(srt_path)}':charenc=UTF-8")
    if logo_text.strip():
        logo_file = output.parent / "logo_watermark.txt"
        logo_file.write_text(logo_text.strip(), encoding="utf-8")
        font = _font_file()
        font_option = f":fontfile='{_escape_filter_path(font)}'" if font else ""
        opacity = min(1.0, max(0.05, float(logo_opacity)))
        size = max(10, int(logo_size))
        period = max(4, int(logo_period))
        filters.append(f"drawtext=textfile='{_escape_filter_path(logo_file)}'{font_option}:fontcolor=white@{opacity}:fontsize={size}:x=(w-text_w)/2:y='(h-text_h)/2 + (h-text_h)/2*sin(2*PI*t/{period})':shadowcolor=black@0.35:shadowx=2:shadowy=2")
    vf = ",".join(filters) if filters else "null"
    _run(["ffmpeg", "-y", "-i", str(video_path), "-i", str(voice_path), "-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(output)])
    return output
