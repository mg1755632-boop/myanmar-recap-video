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
    candidates = [
        "Noto Sans Myanmar",
        "Noto Sans Myanmar UI",
        "Myanmar3",
        "Pyidaungsu",
        "DejaVu Sans",
    ]

    if shutil.which("fc-match"):
        for name in candidates:
            result = subprocess.run(["fc-match", "-f", "%{file}", name], capture_output=True, text=True, check=False)
            path = result.stdout.strip()
            if path and Path(path).exists():
                return path

    for path in [
        "/usr/share/fonts/truetype/noto/NotoSansMyanmar-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansMyanmarUI-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]:
        if Path(path).exists():
            return path

    for font_path in sorted(Path("/usr/share/fonts").rglob("*Myanmar*.ttf")):
        if font_path.exists():
            return str(font_path)

    for font_path in sorted(Path("/usr/share/fonts").rglob("*DejaVuSans*.ttf")):
        if font_path.exists():
            return str(font_path)

    return None


def _subtitle_font_name() -> str:
    # ffmpeg's subtitles filter expects a font family name in force_style, not a file path.
    font_file = _font_file()
    if not font_file:
        return "DejaVu Sans"

    if "NotoSansMyanmar" in font_file or "Myanmar" in font_file:
        return "Noto Sans Myanmar"
    if "Pyidaungsu" in font_file:
        return "Pyidaungsu"
    if "DejaVuSans" in font_file:
        return "DejaVu Sans"
    return "DejaVu Sans"


def _ass_color(hex_color: str) -> str:
    value = hex_color.strip().lstrip("#")
    if len(value) != 6:
        value = "FFFFFF"
    red, green, blue = value[0:2], value[2:4], value[4:6]
    return f"&H00{blue}{green}{red}"


def export_final_video(
    video_path: str | Path,
    voice_path: str | Path,
    srt_path: str | Path,
    output_path: str | Path,
    *,
    burn_subtitles: bool = True,
    blur_video: bool = False,
    blur_strength: int = 2,
    subtitle_size: int = 32,
    subtitle_color: str = "#FFFFFF",
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
        subtitle_font = _subtitle_font_name()
        subtitle_style = (
            f"FontName={subtitle_font},Fontsize={max(12, int(subtitle_size))},"
            f"PrimaryColour={_ass_color(subtitle_color)},OutlineColour=&H80000000,"
            f"Outline=2,Shadow=1,Alignment=2,MarginV=20,Encoding=1"
        )
        filters.append(f"subtitles='{_escape_filter_path(srt_path)}':charenc=UTF-8:force_style='{subtitle_style}'")
    if logo_text.strip():
        logo_file = output.parent / "logo_watermark.txt"
        logo_file.write_text(logo_text.strip(), encoding="utf-8")
        font = _font_file()
        font_option = f":fontfile='{_escape_filter_path(font)}'" if font else ""
        opacity = min(1.0, max(0.05, float(logo_opacity)))
        size = max(10, int(logo_size))
        period = max(4, int(logo_period))
        filters.append(
            f"drawtext=textfile='{_escape_filter_path(logo_file)}'{font_option}:fontcolor=white@{opacity}:fontsize={size}:"
            f"x=(w-text_w)/2:y='(h-text_h)/2 + (h-text_h)/2*sin(2*PI*t/{period})':shadowx=2:shadowy=2:shadowcolor=black@0.5"
        )
    vf = ",".join(filters) if filters else "null"

    # Ensure the final MP4 covers the entire video duration even if the voice-over is shorter.
    try:
        media_info = get_media_info(video_path)
        video_duration = float(media_info.get("duration", 0) or 0.0)
    except VideoError:
        video_duration = 0.0

    ffmpeg_cmd: list[str] = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(voice_path),
        "-vf",
        vf,
    ]

    # If we have a known video duration, pad the audio stream to at least that length using filter_complex.
    # This uses apad and atrim so the audio stream will be extended with silence then trimmed to the exact duration.
    if video_duration and video_duration > 0:
        # add a small margin (1.5s) to be safe for rounding
        pad_target = video_duration + 1.5
        pad_target_str = f"{pad_target:.3f}"
        # filter_complex will create a labeled padded audio stream [padded]
        ffmpeg_cmd.extend([
            "-filter_complex",
            f"[1:a]apad,atrim=0:{pad_target_str}[padded]",
            "-map",
            "0:v:0",
            "-map",
            "[padded]",
        ])
    else:
        ffmpeg_cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])

    ffmpeg_cmd.extend([
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output),
    ])

    _run(ffmpeg_cmd)
    return output
