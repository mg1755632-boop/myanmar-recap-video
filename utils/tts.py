from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

VOICES = {
    "my-MM-NilarNeural": {"label": "Nilar (မြန်မာ အမျိုးသမီးအသံ)", "gender": "Female"},
    "my-MM-ThihaNeural": {"label": "Thiha (မြန်မာ အမျိုးသားအသံ)", "gender": "Male"},
}
SPEEDS = (0.75, 0.85, 1.00, 1.10, 1.25)


class VoiceError(RuntimeError):
    pass


def _rate(speed: float) -> str:
    return f"{(speed - 1) * 100:+.0f}%"


async def _save(text: str, voice: str, rate: str, path: Path) -> None:
    import edge_tts
    await edge_tts.Communicate(text=text, voice=voice, rate=rate).save(str(path))


def generate_voiceover(segments: list[dict], output_path: str | Path, voice: str, speed: float) -> tuple[Path, list[str]]:
    if voice not in VOICES:
        raise VoiceError("Unsupported Burmese voice selected.")
    if speed not in SPEEDS:
        raise VoiceError("Unsupported speaking speed selected.")
    try:
        import edge_tts  # noqa: F401
    except ImportError as exc:
        raise VoiceError("edge-tts is not installed. Run pip install -r requirements.txt.") from exc
    output = Path(output_path)
    work = output.parent / "voice_segments"
    work.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    warnings: list[str] = []
    for index, segment in enumerate(segments):
        text = str(segment.get("burmese", "")).strip()
        if not text:
            continue
        start, end = float(segment["start"]), float(segment["end"])
        target = max(0.1, end - start)
        rate = speed
        path = work / f"segment_{index:04d}.mp3"
        try:
            asyncio.run(_save(text, voice, _rate(rate), path))
            duration_proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], check=True, capture_output=True, text=True)
            duration = float(duration_proc.stdout.strip() or 0)
            if duration > target * 1.08:
                needed = min(1.75, max(0.75, duration / target))
                adjusted = min(1.75, rate * needed)
                asyncio.run(_save(text, voice, _rate(adjusted), path))
                duration = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)], check=True, capture_output=True, text=True).stdout.strip() or 0)
            if duration > target * 1.08:
                warnings.append(f"Segment {index + 1} is longer than its subtitle window ({duration:.1f}s vs {target:.1f}s); it was not cut.")
            files.append(path)
        except Exception as exc:
            raise VoiceError(f"Voice generation failed on segment {index + 1}: {exc}") from exc
    if not files:
        raise VoiceError("There is no Burmese text to synthesize.")
    inputs: list[str] = []
    filters: list[str] = []
    for index, (path, segment) in enumerate(zip(files, [s for s in segments if str(s.get("burmese", "")).strip()])):
        inputs += ["-i", str(path)]
        delay = max(0, int(float(segment["start"]) * 1000))
        filters.append(f"[{index}:a]adelay={delay}|{delay}[a{index}]")
    labels = "".join(f"[a{i}]" for i in range(len(files)))
    filters.append(f"{labels}amix=inputs={len(files)}:duration=longest:dropout_transition=0,apad=pad_dur=0.2[aout]")
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[aout]", "-c:a", "libmp3lame", "-q:a", "2", str(output)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise VoiceError((exc.stderr or "FFmpeg audio mix failed")[-1200:]) from exc
    return output, warnings
