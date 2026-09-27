from __future__ import annotations

from pathlib import Path


class TranscriptionError(RuntimeError):
    pass


def _transcribe_with_assemblyai(audio_path: str | Path, api_key: str) -> tuple[list[dict], str]:
    try:
        import assemblyai as aai
    except ImportError as exc:
        raise TranscriptionError("AssemblyAI fallback selected, but assemblyai is not installed.") from exc
    try:
        aai.settings.api_key = api_key
        transcript = aai.Transcriber().transcribe(str(audio_path))
        if transcript.status == aai.TranscriptStatus.error:
            raise TranscriptionError(f"AssemblyAI transcription failed: {transcript.error}")
        words = list(transcript.words or [])
        if not words:
            raise TranscriptionError("AssemblyAI did not detect speech in the audio.")
        rows: list[dict] = []
        current: list[str] = []
        start_ms = words[0].start
        last_end_ms = words[0].end
        for word in words:
            current.append(word.text)
            last_end_ms = word.end
            sentence_end = word.text.rstrip().endswith((".", "!", "?", "။", "၊"))
            long_segment = (last_end_ms - start_ms) >= 8000
            if sentence_end or long_segment:
                rows.append({"start": round(start_ms / 1000, 3), "end": round(last_end_ms / 1000, 3), "original": " ".join(current).strip()})
                current = []
                if word is not words[-1]:
                    start_ms = word.end
        if current:
            rows.append({"start": round(start_ms / 1000, 3), "end": round(last_end_ms / 1000, 3), "original": " ".join(current).strip()})
        return rows, str(transcript.language_code or "unknown")
    except TranscriptionError:
        raise
    except Exception as exc:
        raise TranscriptionError(f"AssemblyAI transcription failed: {exc}") from exc


def transcribe_audio(audio_path: str | Path, model_size: str = "base", assemblyai_api_key: str | None = None) -> tuple[list[dict], str]:
    if assemblyai_api_key:
        return _transcribe_with_assemblyai(audio_path, assemblyai_api_key)
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
