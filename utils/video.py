from __future__ import annotations

import json
import shlex
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


def export_final_video(video_path: str | Path, voice_path: str | Path, srt_path: str | Path, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    # FFmpeg's subtitles filter needs a safely quoted path, especially on Windows.
    subtitle_path = str(Path(srt_path).resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    vf = f"subtitles='{subtitle_path}':charenc=UTF-8"
    _run(["ffmpeg", "-y", "-i", str(video_path), "-i", str(voice_path), "-vf", vf, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(output)])
    return output
