"""Local CLAP sound verification. The model runs in the render worker, never in the app."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_classifier = None


def _load_classifier():
    global _classifier
    if _classifier is None:
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError("CLAP local absent. Installez requirements-audio-semantic.txt et téléchargez le modèle.") from exc
        model = os.getenv("CLAP_MODEL", "laion/clap-htsat-unfused")
        cache = os.getenv("HF_HOME")
        _classifier = pipeline("zero-shot-audio-classification", model=model, cache_dir=cache, device=-1)
    return _classifier


def compare_audio(path: Path, requested: str, *, threshold: float = 0.55, min_margin: float = 0.15) -> dict[str, Any]:
    """Compare one candidate against the requested sound and explicit alternatives.

    Scores are relative model scores, not calibrated probabilities. A conservative
    winner-plus-margin rule is used; ambiguous clips are rejected.
    """
    if not path.is_file() or not requested.strip():
        return {"status": "rejected", "reason": "Fichier ou description attendue absent."}
    labels = [f"{requested.strip()}", "human speech or dialogue", "music", "an unrelated ambient sound", "silence or near silence"]
    result = _load_classifier()(str(path), candidate_labels=labels, hypothesis_template="The audio contains {}.")
    ranked = sorted(result, key=lambda row: float(row.get("score", 0)), reverse=True)
    if not ranked:
        return {"status": "uncertain", "reason": "Le modèle n’a retourné aucun score."}
    top = ranked[0]
    target = next((r for r in ranked if r.get("label") == labels[0]), None)
    target_score = float(target["score"]) if target else 0.0
    next_score = max((float(r["score"]) for r in ranked if r.get("label") != labels[0]), default=0.0)
    margin = target_score - next_score
    passed = target is not None and top.get("label") == labels[0] and target_score >= threshold and margin >= min_margin
    return {"status": "confirmed" if passed else "rejected", "requested": requested,
            "matched_label": top.get("label"), "score": round(target_score, 4),
            "margin": round(margin, 4), "threshold": threshold,
            "reason": "Correspondance CLAP suffisante." if passed else "La description demandée ne domine pas assez les sons concurrents."}
