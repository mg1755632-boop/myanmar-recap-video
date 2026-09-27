from __future__ import annotations

import json
from typing import Iterable, Mapping


class TranslationError(RuntimeError):
    pass


def translate_segments(segments: Iterable[Mapping[str, object]], api_key: str, model_name: str = "gemini-2.5-flash") -> list[dict]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise TranslationError("google-genai is not installed. Run pip install -r requirements.txt.") from exc
    rows = [dict(item) for item in segments]
    payload = [{"index": i, "start": row["start"], "end": row["end"], "text": row["original"]} for i, row in enumerate(rows)]
    prompt = """Translate each movie/drama recap transcript segment into natural Myanmar Burmese. Preserve meaning, names, places, and important terms. Do not invent or omit information. Make it sound like fluent Burmese recap narration, not word-for-word translation. Keep every timestamp and index unchanged. Return ONLY a JSON array of objects with keys index, start, end, burmese.\n\nSegments:\n""" + json.dumps(payload, ensure_ascii=False)
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        translated = json.loads(response.text)
        by_index = {int(item["index"]): item for item in translated}
        if len(by_index) != len(rows):
            raise TranslationError("Gemini returned an incomplete translation set.")
        result = []
        for i, row in enumerate(rows):
            item = by_index[i]
            result.append({"start": float(row["start"]), "end": float(row["end"]), "original": str(row["original"]), "burmese": str(item.get("burmese", "")).strip()})
        return result
    except TranslationError:
        raise
    except Exception as exc:
        raise TranslationError(f"Gemini translation failed: {exc}") from exc
