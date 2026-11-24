from __future__ import annotations

from typing import Any


def align_scene_narrations(film: dict[str, Any], durations: dict[str, float]) -> tuple[list[dict], list[str]]:
    """Fit each narrated scene to its measured TTS length and place its own segment."""
    tracks: list[dict] = []
    warnings: list[str] = []
    scenes = sorted(film.get("scenes", []), key=lambda item: item.get("order", 0))
    old_spans: list[tuple[float, float]] = []
    new_spans: list[tuple[float, float]] = []
    old_offset = new_offset = 0.0
    for scene in scenes:
        old_duration = max(0.0, float(scene.get("durationSec", 0) or 0))
        actual = float(durations.get(str(scene.get("id", "")), 0) or 0)
        new_duration = actual if actual > 0 and old_duration > 0 else old_duration
        old_spans.append((old_offset, old_offset + old_duration))
        new_spans.append((new_offset, new_offset + new_duration))
        old_offset += old_duration
        new_offset += new_duration

    def remap_time(value: float) -> float:
        for (old_start, old_end), (new_start, new_end) in zip(old_spans, new_spans):
            if old_start <= value <= old_end and old_end > old_start:
                ratio = (new_end - new_start) / (old_end - old_start)
                return new_start + (value - old_start) * ratio
        return value + (new_offset - old_offset) if value > old_offset else value

    # Subtitles use the film's global timeline. Move their cues with scene
    # boundaries so narration timing changes do not desynchronize captions.
    for subtitle_track in film.get("subtitles", []) or []:
        for cue in subtitle_track.get("cues", []) or []:
            if "startSec" in cue:
                cue["startSec"] = round(max(0.0, remap_time(float(cue["startSec"]))), 3)
            if "endSec" in cue:
                cue["endSec"] = round(max(0.0, remap_time(float(cue["endSec"]))), 3)

    # Sound effects and imported dialogue follow the same scene clock as captions.
    if (film.get("info") or {}).get("editorialLevel") in {3, 4, 5}:
        for track in (film.get("audio") or {}).get("tracks", []) or []:
            for event in track.get("events", []) or []:
                start = float(event["startSec"])
                end = start + float(event["durationSec"])
                event["startSec"] = round(remap_time(start), 3)
                event["durationSec"] = round(max(0.001, remap_time(end)-remap_time(start)), 3)

    offset = 0.0
    for scene in scenes:
        scene_id = str(scene.get("id", ""))
        previous_duration = float(scene.get("durationSec", 0) or 0)
        actual = float(durations.get(scene_id, 0) or 0)
        if actual > 0 and previous_duration > 0:
            narration = scene.get("narration") or {}
            target = float(narration.get("targetDurationSec", previous_duration) or previous_duration)
            if abs(actual - target) > max(1.0, target * 0.1):
                warnings.append(
                    f"Narration de la scène {scene.get('order', '')} : durée mesurée différente "
                    f"de la cible après synthèse ({actual:.2f}s contre {target:.2f}s). "
                    "La scène suit la durée réelle de la voix."
                )
            ratio = actual / previous_duration
            for shot in scene.get("shots", []):
                start = max(0.0, float(shot.get("inSec", 0)) * ratio)
                end = max(start + 0.05, float(shot.get("outSec", previous_duration)) * ratio)
                shot["inSec"] = round(start, 3)
                shot["outSec"] = round(end, 3)
            scene["durationSec"] = round(actual, 3)
            media_id = f"__scene_narration_{scene_id}"
            tracks.append({"id": media_id, "kind": "voiceover", "mediaRef": media_id,
                "events": [{"startSec": round(offset, 3), "durationSec": round(actual, 3)}]})
        offset += float(scene.get("durationSec", 0) or 0)
    return tracks, warnings
