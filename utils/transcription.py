from __future__ import annotations

from pathlib import Path


class TranscriptionError(RuntimeError):
    pass


def transcribe_audio(audio_path: str | Path, model_size: str = "base") -> tuple[list[dict], str]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise TranscriptionError("faster-whisper is not installed. Run pip install -r requirements.txt.") from exc
    try:
        model = WhisperModel(model_size, device="auto", compute_type="int8")
        segments, info = model.transcribe(str(audio_path), vad_filter=True, beam_size=5)
        rows = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                rows.append({"start": round(float(segment.start), 3), "end": round(float(segment.end), 3), "original": text})
        if not rows:
            raise TranscriptionError("No speech was detected in the audio.")
        return rows, str(info.language or "unknown")
    except TranscriptionError:
        raise
    except Exception as exc:
        raise TranscriptionError(f"Transcription failed: {exc}") from exc
