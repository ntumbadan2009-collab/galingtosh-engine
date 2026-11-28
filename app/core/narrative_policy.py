"""Evidence-first narrative visual gate shared by the render worker.

A search-result title, tags, a scene cut, or a user-supplied score is NOT
proof of visual relevance. Autonomous scenes use code-rendered narration
cards unless a real image/frame inspection was saved on the specific shot.
The existing manual editing/rending workflow is backwards compatible:
the gate applies only when film.info.visualPolicy == "strict".
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any
from app.core.motion_policy import motion_spec_issues

MIN_RELEVANCE = 0.82
MIN_QUALITY = 0.55
MAX_CODE_CARD_SECONDS = 12.0
MAX_MEDIA_SHOT_SECONDS = 16.0


def _clean(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def excerpt_matches(narration: Any, quote: Any) -> bool:
    """Only exact text from the current scene may drive an illustration."""
    content, excerpt = _clean(narration), _clean(quote)
    return bool(excerpt and len(excerpt) >= 5 and len(excerpt) <= 280 and excerpt in content)


def _finite_score(value: Any, minimum: float) -> bool:
    return (
        type(value) in (float, int)
        and math.isfinite(value)
        and minimum <= value <= 1
    )


def _visual_evidence_valid(shot: dict, media: dict, narration: str) -> bool:
    audit = shot.get("visualEvidence")
    if not isinstance(audit, dict):
        return False
    if audit.get("verifiedBy") != "vision_observation_v1" or audit.get("actualVisualAnalysis") is not True:
        return False
    if audit.get("mediaRef") != shot.get("mediaRef") or not excerpt_matches(narration, audit.get("narrationQuote")):
        return False
    if not _clean(audit.get("visualIntent")) or audit.get("hasContradiction") is not False:
        return False
    if media.get("source") == "search" and audit.get("licenseChecked") is not True:
        return False
    if media.get("kind") not in {"image", "video"}:
        return False
    extended=(media.get("provenance") or {}).get("source") in {"artic","archive","smithsonian","web","polyhaven_preview"}
    if extended and (not re.fullmatch(r"[a-f0-9]{64}",str(audit.get("assetSha256",""))) or audit.get("contentSafetyChecked") is not True):
        return False
    scores = audit.get("samples")
    needed = 3 if media.get("kind") == "video" else 1
    if not isinstance(scores, list) or len(scores) < needed or len(scores) > 4:
        return False
    observed_times = []
    for sample in scores:
        if not isinstance(sample, dict):
            return False
        if (not _finite_score(sample.get("relevance"), MIN_RELEVANCE)
                or not _finite_score(sample.get("visualQuality"), MIN_QUALITY)
                or not _clean(sample.get("description"))
                or sample.get("hasContradiction") is not False):
            return False
        if extended and sample.get("contentSafe") is not True:
            return False
        if media.get("kind") == "video":
            at = sample.get("atSec")
            if type(at) not in (float, int) or not math.isfinite(at):
                return False
            observed_times.append(float(at))
    if media.get("kind") == "video":
        begin = float(shot.get("sourceInSec", 0) or 0)
        span = float(shot.get("outSec", 0)) - float(shot.get("inSec", 0))
        if not (span > 0 and len(set(round(v, 2) for v in observed_times)) >= 3):
            return False
        if any(v < begin - 0.1 or v > begin + span + 0.1 for v in observed_times):
            return False
        if abs(float(audit.get("sourceInSec", -1)) - begin) > 0.1:
            return False
    return True


def narrative_issues(film: dict) -> list[str]:
    """Explain every unsafe autonomous shot. Never silently approve a fallback."""
    scenes = film.get("scenes") or []
    media_index = {
        m.get("id"): m for m in (film.get("media") or [])
        if isinstance(m, dict) and isinstance(m.get("id"), str)
    }
    problems = []
    for si, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            problems.append(f"Scène {si+1} invalide.")
            continue
        narration = (scene.get("narration") or {}).get("text") or scene.get("narrativeGoal", "")
        shots = scene.get("shots") or []
        if not shots:
            problems.append(f"Scène {si+1} sans plans illustrés.")
            continue
        if not _clean(narration):
            problems.append(f"Scène {si+1} sans narration de référence.")
            continue
        for pi, shot in enumerate(shots):
            if not isinstance(shot, dict):
                problems.append(f"Plan {si+1}.{pi+1} invalide.")
                continue
            try:
                duration = float(shot.get("outSec", 0)) - float(shot.get("inSec", 0))
            except (ValueError, TypeError):
                duration = 0
            if not math.isfinite(duration) or duration <= 0:
                problems.append(f"Plan {si+1}.{pi+1} avec durée invalide.")
                continue
            mode = shot.get("visualMode")
            if mode == "programmatic":
                if (shot.get("mediaRef") or not excerpt_matches(narration, shot.get("visualText"))):
                    problems.append(f"Plan {si+1}.{pi+1} : illustration par code sans extrait fidèle de narration.")
                if duration > MAX_CODE_CARD_SECONDS:
                    problems.append(f"Plan {si+1}.{pi+1} : carte trop longue (> {MAX_CODE_CARD_SECONDS:g}s).")
                for issue in motion_spec_issues(narration, shot.get("visualText"), shot.get("visualSpec")):
                    problems.append(f"Plan {si+1}.{pi+1} : {issue}")
            else:
                media = media_index.get(shot.get("mediaRef"))
                if not media or not _visual_evidence_valid(shot, media, narration):
                    problems.append(f"Plan {si+1}.{pi+1} : pertinence média non prouvée par vision. Analyser le plan ou utiliser une illustration par code.")
                if duration > MAX_MEDIA_SHOT_SECONDS:
                    problems.append(f"Plan {si+1}.{pi+1} : plan trop long (> {MAX_MEDIA_SHOT_SECONDS:g}s).")
    return problems


def validate_narrative_policy(film: dict) -> None:
    if (film.get("info") or {}).get("visualPolicy") == "strict":
        issues = narrative_issues(film)
        if issues:
            raise ValueError("Montage narratif non vérifié : " + " ".join(issues[:5]))
