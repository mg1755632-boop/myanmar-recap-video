from __future__ import annotations

from typing import Iterable, Mapping


def _timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    millis = int(round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def segments_to_srt(segments: Iterable[Mapping[str, object]]) -> str:
    blocks: list[str] = []
    for index, segment in enumerate(segments, 1):
        text = str(segment.get("burmese", "")).strip()
        if not text:
            continue
        start = float(segment.get("start", 0))
        end = max(start + 0.1, float(segment.get("end", start + 0.1)))
        blocks.append(f"{index}\n{_timestamp(start)} --> {_timestamp(end)}\n{text}\n")
    return "\n".join(blocks) + ("\n" if blocks else "")
